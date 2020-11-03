import contextlib
import hashlib
import importlib
import re
import os
import pprint
import sys
import types
import contextlib
import subprocess

from violet.lexer import lexer
from violet.objects import Void
from violet.parser import parser
from violet import vast as ast
from violet.errors import *
from violet.errors import _Exit
from violet import objects
from violet._util import IndexableNamespace

_STD_TYPES = {
	'nil': objects.Void,
	'List': objects.List,
	'String': objects.String,
	'Void': objects.Void,
	'Integer': objects.Integer,
	'Boolean': objects.Boolean
}

_PY_TYPES = {
	int: objects.Integer,
	str: objects.String,
	type(None): objects.Void,
	list: objects.List.from_value0
}

_print = print
def print(*args, **kwargs):
	kwargs['file'] = kwargs.get('file', sys.stderr)
	_print(*args, **kwargs)

class VarNotFound(Exception):
	def __init__(self, var):
		super().__init__(f"variable {var.name!r} is not defined")

class CannotReassignConst(Exception):
	def __init__(self, var):
		super().__init__(f"constant variable {var.name!r} cannot be reassigned")

class Scope:
	def __init__(self, runner):
		self.runner = runner
		self.vars = {}
		self.const_vars = {}
		self.parent = None

		self.hash = hashlib.sha1(os.urandom(16)).hexdigest()
		# print("spawned scope", self.hash)

	def __repr__(self):
		return "Scope(" + repr(self.vars) + ", " + repr(self.const_vars) + ")"

	def is_var_assigned(self, identifier, recurse=True):
		return \
			identifier in self.vars or \
			identifier in self.const_vars or \
			identifier.name in _STD_TYPES or \
			(recurse and self.parent and self.parent.is_var_assigned(identifier))

	def get_var_noid(self, name):
		return self.get_var(ast.Identifier(name, -1))

	def get_var(self, identifier):
		# print(self.hash, ": getting", identifier)
		try:
			if identifier.name in _STD_TYPES:
				return _STD_TYPES[identifier.name]
			var = self.vars.get(identifier)
			if var is None:
				var = self.const_vars.get(identifier)
			if var is None:
				raise VarNotFound(identifier)
			return var
		except VarNotFound:
			if not self.parent:  # self.parent?.getVar(identifier) ?: throw error
				raise
			return self.parent.get_var(identifier)

	def reassign_var(self, identifier, value, *, const=None):  # pointless const argument, just for safety
		# print("reassign", identifier, value)
		if identifier in self.const_vars:
			raise CannotReassignConst(identifier)  # cannot reassign consts
		orig = ast.TypeId(ast.Identifier(self.vars[identifier].__class__.__name__, identifier.lineno))
		orig.type_check(value, self.runner)
		self.vars[identifier] = value

	def set_var(self, identifier, value, *, const=False):
		# print(self.hash, ": assigning", identifier, value)
		if not isinstance(value, (objects.Object, objects.ThinPythonObjectWrapper)):
			if isinstance(value, type):
				value = objects.ThinPythonTypeWrapper(value)
			else:
				value = objects.ThinPythonObjectWrapper(value)
		# print("assigning", identifier, "to", value, "as const?", const)
		if self.is_var_assigned(identifier, False):
			print(f"WARN: shadowing variable {identifier.transform_to_string()!r}")
		if const:
			# print("set const var")
			self.const_vars[identifier] = value
		else:
			# print("set var")
			self.vars[identifier] = value

class Runner:
	def __init__(self, code, *, filename="<string>", debug=False, write_ast=False):
		self.debug = debug
		self.global_scope = gl = Scope(self)
		self.scopes = {gl.hash: gl}
		self.active_scope = gl.hash
		self.code = code
		self.filename = filename
		self.lineno = 0
		self.write_ast = write_ast

	@staticmethod
	def wrap_py_type(value):
		return _PY_TYPES[type(value)](value, runner=self)

	def get_var(self, *args, **kwargs):
		return self.get_current_scope().get_var(*args, **kwargs)

	def get_current_scope(self):
		return self.scopes[self.active_scope]

	@classmethod
	def open(cls, fp, **kwargs):
		with open(fp) as f:
			return cls(f.read(), filename=fp, **kwargs)

	def interpret(self):
		module = ast.Module([])
		body = parser.parse(lexer.tokenize(self.code))
		if parser._error_list:
			for error in parser._error_list:
				print(f"ERROR:{error.lineno}: Unexpected {error.value!r}")
			parser._error_list.clear()
			sys.exit(1)

		module.body.extend(body)
		# print(module, file=sys.stdout)
		try:
			# print(module.body)
			self.exec_module(module)
		except Panic as e:
			print("FATAL: system error occured:", e, file=sys.stderr)
			sys.exit(9)
		except StatementError as e:
			if self.debug:
				raise
			print(f"ERROR:{e.stmt.lineno}: {e}")
			sys.exit(1)

		except RuntimeException as e:
			print(f"Exception: {e.stmt.lineno} {e.message}")
		# print(self.get_current_scope())
		# pprint.pprint(self.scopes)
		# return self
		if self.write_ast:
			with open("test_out.py", "w") as f:
				print(module, file=f)
			subprocess.run(["black", "test_out.py"], capture_output=True)
		return self

	@property
	def argv(self):
		# TODO: sys.argv
		return ast.Primitive(IndexableNamespace(value=[ast.Primitive(IndexableNamespace(value='"a"',lineno=-1),objects.String)],lineno=-1),objects.List).eval(self)

	def run(self):
		try:
			main = self.get_current_scope().get_var(ast.Identifier('main', -1))
		except VarNotFound:
			print(f"FATAL: missing entry point function 'main' in file {self.filename}", file=sys.stderr)
			sys.exit(1)

		try:
			with self.new_scope():
				# print(main, dir(main))
				if len(main.params) == 1:
					main([self.argv], runner=self)	
				else:
					main([], runner=self)
		except StatementError as e:
			if self.debug:
				raise
			print(f"ERROR:{e.stmt.lineno}:", e)
			sys.exit(1)
		except Exception as e:
			if self.debug:
				raise
			print(f"ERROR:{main.lineno}:", e)
			sys.exit(1)

	@contextlib.contextmanager
	def new_scope(self):
		scope = Scope(self)
		scope.parent = self.get_current_scope()
		self.scopes[scope.hash] = scope
		old_scope = self.active_scope
		# print("opening scope", scope.hash, "with parent", old_scope)
		self.active_scope = scope.hash
		try:
			yield
		finally:
			# print("closing scope", scope.hash, "to", old_scope)
			self.active_scope = old_scope

	def exec_module_body(self, stmt_list):
		for statement in stmt_list:
			# print("MODULE: executing", statement.__class__.__name__, getattr(statement, 'name', None))

			try:
				if isinstance(statement, ast.Import):
					self._exec_import(statement)
				elif isinstance(statement, ast.Assignment):
					self._exec_assignment(statement)
				elif isinstance(statement, ast.Reassignment):
					self._exec_assignment(statement, True)
				elif isinstance(statement, ast.Function):
					self._exec_function_spawn(statement)
				else:
					raise StatementError(statement, f'unexpected {statement.__class__.__name__!r} statement')
			except Exception as e:
				if isinstance(e, (StatementError, _Exit)):
					raise
				raise StatementError(statement, str(e))

	def exec_function_body(self, body, func):
		for statement in body:
			# print("FUNCTION: executing", statement.__class__.__name__, getattr(statement, 'name', None))
			try:
				if isinstance(statement, ast.Assignment):
					self._exec_assignment(statement)
				elif isinstance(statement, ast.Reassignment):
					self._exec_assignment(statement, True)
				elif isinstance(statement, ast.Return):
					self._exec_return(statement, func)
				elif isinstance(statement, ast.Break):
					raise BreakExit
				elif isinstance(statement, ast.Continue):
					raise ContinueExit
				elif isinstance(statement, ast.FunctionCall):
					statement.eval(self)
				elif isinstance(statement, ast.Control):
					statement.eval(self, func)
				else:
					raise StatementError(statement, f'unexpected {statement.__class__.__name__!r} statement')
			except Exception as e:
				if isinstance(e, (StatementError, _Exit, RuntimeException)):
					raise
				raise StatementError(statement, str(e))

	def exec_module(self, module):
		self.exec_module_body(module.body)

	def _exec_import(self, stmt):
		form = stmt.from_module
		if isinstance(form, ast.Attribute):
			if form.transform_to_string().startswith("std"):
				return self._exec_std_import(stmt)
			return self._exec_local_import(stmt)

		else:
			if form.name == 'std':
				return self._exec_std_import(stmt)
			return self._exec_local_import(stmt)

	def _exec_std_import(self, stmt):
		# print(stmt)
		form = stmt.from_module
		name = form.transform_to_string()
		vi_file_name = os.path.join("violet", *name.split(".")) + ".vi"
		is_vi_file = os.path.exists(vi_file_name)
		if is_vi_file:
			try:
				module = Runner.open(vi_file_name)
				module.interpret()
			except Exception as e:
				raise StatementError(stmt, f'module {stmt.from_module.name!r} does not exist')

			else:
				for identifier in stmt.importing:
					if identifier.name == "*":
						vars = module.get_current_scope().vars
						scope = self.get_current_scope()
						for ident, value in vars.items():
							scope.set_var(ident, value)

						break

					else:
						try:
							var = module.get_current_scope().get_var(identifier)
						except Exception as e:
							raise StatementError(stmt, f'failed to import {identifier.name!r} from {name}')
						else:
							self.get_current_scope().set_var(identifier, var)

		else:
			try:
				module = importlib.import_module('violet.'+name)
			except ImportError:
				raise StatementError(stmt, f'module {name!r} does not exist')
			else:
				for iport in stmt.importing:
					if iport.name == "*":
						if not hasattr(module, "__all__"):
							importables = (x for x in dir(module) if x.isalpha() or not x.startswith("__"))

						else:
							importables = module.__all__

						scope = self.get_current_scope()
						for vname in importables:
							scope.set_var(ast.Identifier(vname, stmt.lineno), getattr(module, vname))

						break

					if not hasattr(module, iport.name):
						raise StatementError(stmt, f'failed to import {iport.name!r} from {name!r}')
					else:
						self.get_current_scope().set_var(iport, getattr(module, iport.name))

	def _exec_local_import(self, stmt):
		try:
			new = Runner.open(stmt.from_module.name+'.vi')
			new.interpret()
		except FileNotFoundError:
			raise StatementError(stmt, f'module {stmt.from_module.name!r} does not exist')

		for name in stmt.importing:
			if name.name == "*":
				vars = new.get_current_scope().vars
				scope = self.get_current_scope()
				for ident, value in vars.items():
					scope.set_var(ident, value)

				break

			try:
				var = new.get_current_scope().get_var(name)
			except Exception as e:
				raise StatementError(stmt, f'failed to import {name.name!r} from {stmt.from_module.name!r}')
			else:
				self.get_current_scope().set_var(name, var)

	def _exec_assignment(self, statement, reassign=False):
		# print(statement, reassign)
		scope = self.global_scope if not reassign and statement.global_scope else self.get_current_scope()
		try:
			expr = statement.expression.eval(self)
		except Exception as e:
			raise StatementError(statement, str(e))
		# print(expr)
		if reassign:
			if not scope.is_var_assigned(statement.identifier):
				raise StatementError(statement, f'variable {statement.identifier.name!r} is not defined')
			meth = scope.reassign_var
		else:
			typ = statement.type
			if typ is not None:
				typ.type_check(expr, self)

			meth = scope.set_var

		try:
			# print(meth)
			meth(statement.identifier, expr, const=statement.constant)
		except Exception as e:
			raise StatementError(statement, str(e))

	def _exec_return(self, statement, func):
		# print(statement)
		expr = statement.expr
		if expr is None or isinstance(expr, Void):
			ret = Void()
		else:
			ret = expr.eval(self)
		if func.return_type is None:
			if not isinstance(ret, objects.Object):
				ret = self.wrap_py_type(ret)
			func.return_type = ret.get_type()
		func.return_type.type_check(ret, self)
		func._return = ret
		raise ReturnExit

	def _exec_function_spawn(self, stmt):
		# print("spawn function")

		self.get_current_scope().set_var(stmt.name, stmt.eval(self))
	