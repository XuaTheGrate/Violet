from violet.errors import *
from violet import objects
import ast as pyast
from types import BuiltinMethodType as PyMethodType
from violet._util import IndexableNamespace

class VioletASTBase:
	__slots__ = 'lineno',
	cls_name = "pp"

	def __init__(self, prod):
		self.lineno = prod.lineno

	def __repr__(self):
		return "{0.__class__.__name__}({1})".format(self, ', '.join(
			'%s=%r' % (i, getattr(self, i))
			for i in self.__slots__
			if not i.startswith('_')
		))

	def eval(self, runner):
		pass

	def __getattr__(self, name):
		try:
			return super().__getattribute__(name)
		except AttributeError:
			raise AttributeError(f'{self.__class__.__name__!r} object has no attribute {name!r}')

class Module(VioletASTBase):
	__slots__ = ('body',)
	cls_name = "module"

	def __init__(self, body):
		super().__init__(IndexableNamespace(lineno=-1))
		self.body = body

class Primitive(VioletASTBase):
	__slots__ = ('value', 'type')
	cls_name = "primitive"

	def __init__(self, prod, type):
		super().__init__(prod)
		if hasattr(prod, 'BRACK_OPEN'):
			self.value = getattr(prod, 'expr_list', [])
		else:
			self.value = prod[0]
		self.type = type

	def eval(self, runner):
		if self.type is objects.Void:
			return objects.Void()
		elif self.type is objects.Boolean:
			return self.type(self.value == 'true')
		elif self.type is objects.Integer:
			return self.type(int(self.value))
		elif self.type is objects.String:
			return self.type(pyast.literal_eval(self.value))
		elif self.type is objects.List:
			return self.type.from_value0(self.value, runner=runner)
		else:
			raise Exception(self.type)

class Identifier(VioletASTBase):
	__slots__ = ('name',)
	cls_name = "identifier"

	def __init__(self, name, lineno):
		super().__init__(IndexableNamespace(lineno=lineno))
		self.name = name

	@classmethod
	def from_production(cls, p):
		return cls(p.IDENTIFIER, p.lineno)

	def __eq__(self, other):
		return isinstance(other, self.__class__) and other.name == self.name

	def __hash__(self):
		return self.name.__hash__()

	def transform_to_string(self):
		return self.name

	def get_top_level_name(self):
		return self

	def eval(self, runner):
		return runner.get_current_scope().get_var(self)

class Attribute(Identifier):
	__slots__ = ('name', 'value')
	cls_name = "attribute"

	def __init__(self, name, value, lineno):
		super().__init__(name, lineno)
		self.value = value

	@classmethod
	def from_production(cls, p):
		return cls(p.identity, p.name, p.lineno)

	def transform_to_string(self):
		return self.name.transform_to_string() + '.' + self.value.transform_to_string()

	def get_top_level_name(self):
		return self.name.get_top_level_name()

class Subscript(VioletASTBase):
	__slots__ = ('name', 'index')
	cls_name = "subscript"

	def __init__(self, name, index):
		self.name = name
		self.index = index

	def eval(self, runner):
		return self.name.eval(runner)

class TypeId(VioletASTBase):
	__slots__ = ('name',)

	def __init__(self, name):
		self.name = name

	def eval(self, runner):
		return self.name.eval(runner)

	def type_check(self, value, runner):
		# print(self.name, value)
		if isinstance(self.name, Subscript):
			supert = self.name.name  # Identifier('List')
			subtypes = self.name.index  # [Identifier('String')]

			typ = runner.get_current_scope().get_var(supert)
			if not isinstance(value, typ):
				raise Exception(f"invalid type {value.__class__.__name__!r} for function call (expected {typ.__name__!r})")
		else:  # single type, eg Identifier('String')
			# print("single")
			typ = runner.get_current_scope().get_var(self.name)
			# print(value, typ, isinstance(value, typ))
			if not isinstance(value, typ):
				raise Exception(f"invalid type {value.__class__.__name__!r} for function call (expected {typ.__name__!r})")

class Import(VioletASTBase):
	__slots__ = ('importing', 'from_module')

	def __init__(self, prod):
		super().__init__(prod)
		self.importing = prod[2]

		if self.importing == "*":
			self.importing = [Identifier(name="*", lineno=prod.lineno)]

		self.from_module = prod.identity

class Assignment(VioletASTBase):
	__slots__ = ('global_scope', 'constant', 'identifier', 'type', 'expression')

	def __init__(self, prod):
		super().__init__(prod)
		self.global_scope = prod.SCOPE == 'put'
		self.constant = getattr(prod, 'CONST', None) is not None
		self.identifier = prod.name
		self.type = getattr(prod, 'typ', None)
		self.expression = prod.expr

class Reassignment(VioletASTBase):
	__slots__ = 'identifier', 'expression', 'constant'

	def __init__(self, prod):
		super().__init__(prod)
		self.identifier = prod.name
		self.expression = prod.expr
		self.constant = False

class Parameter(VioletASTBase):
	__slots__ = ('name', 'type')

	def __init__(self, name, type):
		self.name = name
		self.type = type

class TernaryQMark(VioletASTBase):
	__slots__ = 'expr0', 'expr1', 'expr2'

	def __init__(self, prod):
		super().__init__(prod)
		for i in self.__slots__:
			setattr(self, i, getattr(prod, i))

	def eval(self, runner):
		# print(self)
		# print(self.expr0, self.expr1, self.expr2)
		q = self.expr0.eval(runner)
		if not isinstance(q, objects.Boolean):
			raise Exception(f"expected \"Boolean\" in ternary, found {q.__class__.__name__!r}")

		left = self.expr1.eval(runner)
		right = self.expr2.eval(runner)

		if not isinstance(right, left.__class__):
			raise Exception(f"mismatched types in ternary: {left.__class__.__name__!r} and {right.__class__.__name__!r}")

		if q.value0:
			return left
		return right

class Function(VioletASTBase):
	__slots__ = ('name', 'params', 'ret_value', 'body')

	def __init__(self, prod):
		super().__init__(prod)
		"""
	@_("FUN name PAREN_OPEN param_list PAREN_CLOSE block")
	@_("FUN name PAREN_OPEN param_list PAREN_CLOSE COLON typ block")
	@_("FUN name PAREN_OPEN PAREN_CLOSE block")
	@_("FUN name PAREN_OPEN PAREN_CLOSE COLON typ block")
		"""
		self.name = prod.name
		self.params = getattr(prod, 'param_list', [])
		self.ret_value = getattr(prod, 'typ', None)
		self.body = prod.block
		self.lineno = prod.lineno

	def eval(self, runner):
		return objects.Function(self.name, self.params, self.ret_value, self.body, self.lineno)

class Break(VioletASTBase):
	pass

class Continue(VioletASTBase):
	pass

class Lambda(VioletASTBase):
	__slots__ = ("params", "body")

	def __init__(self, prod):
		super().__init__(prod)
		self.params = getattr(prod, "param_list", [])
		self.body = prod.expr
		self.lineno = prod.lineno

	def eval(self, runner):
		return objects.Lambda(self.params, self.body, self.lineno)

class FunctionCall(VioletASTBase):
	__slots__ = ('name', 'args')

	def __init__(self, prod):
		super().__init__(prod)
		name, args = prod.identity, getattr(prod, 'arg_list', [])
		self.name = name
		self.args = args

	def eval(self, runner):
		name = self.name.get_top_level_name()
		obj = runner.get_current_scope().get_var(name)
		attrs = self.name.transform_to_string().split('.')[1:]
		for attr in attrs:
			try:
				obj = getattr(obj, attr)
			except AttributeError:
				raise HasNoAttribute(obj, attr)

		args = self.args
		transformed = [o.eval(runner) for o in args]

		viobj = getattr(obj, '__self__', None)
		if viobj is not None:
			viobj = issubclass(viobj, objects.Object)

		if not viobj and not isinstance(obj, objects.Function) and not hasattr(obj, '_0_identifies_as_violet'):
			value = obj(*transformed)
		else:
			if isinstance(obj, objects.Function):
				obj(transformed, runner=runner)
				value = obj.reset_state()
			else:
				value = obj(transformed, runner=runner)
		return value

class Return(VioletASTBase):
	__slots__ = 'expr',

	def __init__(self, expr):
		self.expr = expr or objects.Void()

class Cast(VioletASTBase):
	__slots__ = 'expr', 'type'

	def __init__(self, prod):
		super().__init__(prod)
		self.expr = prod.expr
		self.type = prod.typ

	def eval(self, runner):
		obj = self.expr.eval(runner)
		typ = self.type.eval(runner)
		return obj.cast0(typ)

class Control(VioletASTBase):
	def eval(self, runner, func):
		pass

class IfControl(Control):
	__slots__ = 'if_stmt', 'elseif_chain', 'else_stmt'

	def __init__(self, prod):
		super().__init__(IndexableNamespace(lineno=prod.if_stmt.lineno))
		for name in self.__slots__:
			attr = getattr(prod, name, None)
			# print(name, attr)
			setattr(self, name, attr)

	def eval(self, runner, func):
		can = self.if_stmt.eval(runner, func)
		# print("IF ->", can)
		if not can and self.elseif_chain:
			for stmt in self.elseif_chain:
				can = stmt.eval(runner, func)
				if can:
					break
			# print("ELSEIF ->", can)
		if not can and self.else_stmt:
			self.else_stmt.eval(runner, func)
			# print("ELSE")

class ForControl(Control):
	__slots__ = 'name', 'expr', 'body'

	def __init__(self, prod):
		super().__init__(prod)
		# @_("FOR PAREN_OPEN name IN expr PAREN_CLOSE block")
		self.name = prod.name
		self.expr = prod.expr
		self.body = prod.block

	def eval(self, runner, func):
		it = self.expr.eval(runner)
		try:
			it = iter(it)
		except TypeError:
			raise Exception(f"cannot loop over non-iterable type {it.__class__.__name__!r}")
		for i in it:
			with runner.new_scope():
				runner.get_current_scope().set_var(self.name, i, const=True)
				try:
					runner.exec_function_body(self.body, func)
				except BreakExit:
					break
				except ContinueExit:
					continue

class WhileControl(Control):
	pass  # todo

class LoopControl(Control):
	pass  # todo

class SwitchControl(Control):
	pass  # todo

class TryControl(Control):
	__slots__ = "block", "catch_list", "finally_block"
	def __init__(self, prod):
		super().__init__(prod)
		self.block = prod.block if len(prod) == 3 else prod.block0
		if hasattr(prod, "FINALLY"):
			self.finally_block = prod.block1
		else:
			self.finally_block = None

		self.catch_list = prod.catch_list

	def eval(self, runner, func):
		try:
			with runner.new_scope():
				runner.exec_function_body(self.block, func)
		except RuntimeException as e:
			for catcher in self.catch_list:
				typ = catcher.exception_type.eval(runner)
				typ = typ._actual_pytype

				if isinstance(e, typ):
					catcher.eval(runner, func, e)

				break

		finally:
			if self.finally_block is not None:
				with runner.new_scope():
					runner.exec_function_body(self.finally_block, func)


class NilOrElse(Control):
	__slots__ = ('expr0', 'expr1')

	def __init__(self, prod):
		super().__init__(prod)
		self.expr0 = prod.expr0
		self.expr1 = prod.expr1

	def eval(self, runner):
		left = runner.get_var(self.expr0) if isinstance(self.expr0, Identifier) else self.expr0.eval(runner)
		right = runner.get_var(self.expr1) if isinstance(self.expr1, Identifier) else self.expr1.eval(runner)
		# sprint(f"{self.expr0!r}: {left!r}")
		# print(f"{self.expr1!r}: {right!r}")
		if isinstance(left, objects.Void):
			return right
		return left

class If(Control):
	__slots__ = 'expr', 'body'

	def __init__(self, prod):
		super().__init__(prod)
		self.expr = prod.expr
		self.body = prod.block

	def eval(self, runner, func):
		expr = self.expr.eval(runner)
		# print(self.__class__.__name__, "->", self.expr)
		if not isinstance(expr, objects.Boolean):
			raise Exception(f"unexpected type {expr.__class__.__name__!r} (expected \"Boolean\")")
		if expr:
			with runner.new_scope():
				runner.exec_function_body(self.body, func)
		return expr

class ElseIf(Control):
	__slots__ = 'expr', 'body'

	def __init__(self, prod):
		super().__init__(prod)
		self.expr = prod.expr
		self.body = prod.block

	def eval(self, runner, func):
		return If.eval(self, runner, func)

class Else(Control):
	__slots__ = 'body',

	def __init__(self, prod):
		super().__init__(prod)
		self.body = prod.block

	def eval(self, runner, func):
		with runner.new_scope():
			runner.exec_function_body(self.body, func)

class Catch(Control):
	__slots__ = "body", "exception_name", "exception_type"

	def __init__(self, prod):
		super().__init__(prod)
		self.body = prod.block
		self.exception_name = prod.name
		self.exception_type = prod.typ

	def eval(self, runner, func, exception):
		with runner.new_scope():
			runner.get_current_scope().set_var(self.exception_name, exception)
			runner.exec_function_body(self.body, func)

class Throw(Control):
	__slots__ = "error",
	def __init__(self, prod):
		super().__init__(prod)
		self.error = prod.expr

	def eval(self, runner, func):
		exception = self.error.eval(runner)
		raise exception.obj

class Operator:
	__slots__ = ()

	def __repr__(self):
		return '{0.__class__.__name__}()'.format(self)

# math

class Plus(Operator):
	pass

class Minus(Operator):
	pass

class Times(Operator):
	pass

class Divide(Operator):
	pass

class Modulus(Operator):
	pass

class Range(Operator):
	pass

# equality

class EqualTo(Operator):
	pass

class NotEqualTo(Operator):
	pass

class GreaterThan(Operator):
	pass

class GreaterOrEqual(Operator):
	pass

class LessThan(Operator):
	pass

class LessOrEqual(Operator):
	pass

class BiOperatorExpr(VioletASTBase):
	__slots__ = ('left', 'op', 'right')

	def __init__(self, left, op, right):
		self.left = left
		self.op = op
		self.right = right

	def _Plus(self, l, r):
		return l + r

	def _Minus(self, l, r):
		return l - r

	def _Times(self, l, r):
		return l * r

	def _Divide(self, l, r):
		return l // r

	def _Modulus(self, l, r):
		return l % r

	def _EqualTo(self, l, r):
		return l == r

	def _NotEqualTo(self, l, r):
		return l != r

	def _GreaterThan(self, l , r):
		return l > r

	def _GreaterOrEqual(self, l, r):
		return l >= r

	def _LessThan(self, l, r):
		return l < r

	def _LessOrEqual(self, l, r):
		return l <= r

	def _Range(self, l, r):
		return l.get_special_method('..')(r)

	def eval(self, runner):
		left = runner.get_var(self.left) if isinstance(self.left, Identifier) else self.left.eval(runner)
		right = runner.get_var(self.right) if isinstance(self.right, Identifier) else self.right.eval(runner)

		return getattr(self, '_' + self.op.__class__.__name__)(left, right)
