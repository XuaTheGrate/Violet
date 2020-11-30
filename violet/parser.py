import copy
import typing

from sly import Parser

from violet.lexer import VioletLexer
from violet import vast as ast
from violet import objects

def getanyattr(obj, *names):
	for name in names:
		o = getattr(obj, name, ...)
		if o is not ...:
			return o

class VioletParser(Parser):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._error_list = []

	# debugfile = 'parsetab.out'
	tokens = VioletLexer.tokens
	expected_shift_reduce = 2

	precedence = (
		('left', "tern"),
		('left', "lambda"),
		('nonassoc', "type_check"),
		('nonassoc', EQ, NE, GT, GE, LT, LE, RANGE),
		('left', DQMARK),
		('left', MODULUS),
		('left', DIVIDE, MULTIPLY),
		('left', PLUS, MINUS),
	)

	# statements

	@_("stmt")
	@_("stmt_list stmt")
	def stmt_list(self, p):
		# print("stmt_list")
		orig = getanyattr(p, 'stmt_list')
		if orig:
			return orig + [p.stmt]
		return [p.stmt]

	@_("expr EOS")
	@_("iport EOS")
	@_("assign EOS")
	@_("reassign EOS")
	# @_("func_call EOS")
	@_("func")
	@_("return_stmt EOS")
	@_("break_stmt EOS")
	@_("continue_stmt EOS")
	@_("control")
	@_("throw_stmt EOS")
	def stmt(self, p):
		return p[0]

	@_("SCOPE name EQUALS expr")
	@_("SCOPE CONST name EQUALS expr")
	def assign(self, p):
		stmt = ast.Assignment(p)
		# print(stmt)
		return stmt

	@_("SCOPE name COLON typ EQUALS expr")
	@_("SCOPE CONST name COLON typ EQUALS expr")
	def assign(self, p):
		stmt = ast.Assignment(p)
		# print(stmt)
		return stmt

	@_("name EQUALS expr")
	def reassign(self, p):
		return ast.Reassignment(p)

	# expressions

	@_("expr_list COMMA expr")
	@_("expr")
	def expr_list(self, p):
		if len(p) == 3:
			return [*p.expr_list, p.expr]
		return [p.expr]

	@_("expr QMARK expr COLON expr %prec tern")
	def expr(self, p):
		return ast.TernaryQMark(p)

	@_("func_call")
	def expr(self, p):
		return p.func_call

	@_("expr RANGE expr")
	def expr(self, p):
		return ast.BiOperatorExpr(p.expr0, ast.Range(), p.expr1)

	@_("expr PLUS expr")
	def expr(self, p):
		return ast.BiOperatorExpr(p.expr0, ast.Plus(), p.expr1)

	@_("expr MINUS expr")
	def expr(self, p):
		return ast.BiOperatorExpr(p.expr0, ast.Minus(), p.expr1)

	@_("expr MULTIPLY expr")
	def expr(self, p):
		return ast.BiOperatorExpr(p.expr0, ast.Times(), p.expr1)

	@_("expr DIVIDE expr")
	def expr(self, p):
		return ast.BiOperatorExpr(p.expr0, ast.Divide(), p.expr1)

	@_("expr MODULUS expr")
	def expr(self, p):
		return ast.BiOperatorExpr(p.expr0, ast.Modulus(), p.expr1)

	@_("identity")
	def expr(self, p):
		return p.identity

	@_("bool")
	def expr(self, p):
		return p.bool

	@_("expr CAST typ")
	def expr(self, p):
		return ast.Cast(p)

	@_("lambda_expr")
	def expr(self, p):
		return p.lambda_expr

	@_("expr EQ expr")
	def bool(self, p):
		# print(*p)
		return ast.BiOperatorExpr(p.expr0, ast.EqualTo(), p.expr1)

	@_("expr NE expr")
	def bool(self, p):
		return ast.BiOperatorExpr(p.expr0, ast.NotEqualTo(), p.expr1)

	@_("expr GT expr")
	def bool(self, p):
		return ast.BiOperatorExpr(p.expr0, ast.GreaterThan(), p.expr1)

	@_("expr GE expr")
	def bool(self, p):
		return ast.BiOperatorExpr(p.expr0, ast.GreaterOrEqual(), p.expr1)

	@_("expr LT expr")
	def bool(self, p):
		return ast.BiOperatorExpr(p.expr0, ast.LessThan(), p.expr1)

	@_("expr LE expr")
	def bool(self, p):
		return ast.BiOperatorExpr(p.expr0, ast.LessOrEqual(), p.expr1)

	@_("expr ANON_CHECK typ %prec type_check")
	def bool(self, p):
		return ast.BiOperatorExpr(p.expr, ast.TypeCheck(), p.typ)

	"""
	@_("identity ATTR IDENTIFIER")
	@_("IDENTIFIER")
	def identity(self, p):
		# print("attr ident", p.IDENTIFIER)
		return ast.Identifier(p.IDENTIFIER, getanyattr(p, 'identity'))

	"""
	@_("IDENTIFIER")
	def name(self, p):
		return ast.Identifier.from_production(p)

	@_("identity ATTR name")
	# @_("name ATTR name")
	@_("name")
	def identity(self, p):
		# print("attr ident", p.IDENTIFIER)
		if len(p) == 3:
			return ast.Attribute.from_production(p)
		return p.name
		
	# """

	@_("primitive")
	def expr(self, p):
		return p.primitive

	@_('DECIMAL')
	def primitive(self, p):
		prim = ast.Primitive(p, objects.Integer)
		# print(prim)
		return prim

	@_('STRING')
	def primitive(self, p):
		prim = ast.Primitive(p, objects.String)
		# print(prim)
		return prim

	@_('TRUE')
	@_('FALSE')
	def primitive(self, p):
		return ast.Primitive(p, objects.Boolean)

	@_('NIL')
	def primitive(self, p):
		return ast.Primitive(p, objects.Void)

	@_('BRACK_OPEN expr_list BRACK_CLOSE')
	@_('BRACK_OPEN BRACK_CLOSE')
	def primitive(self, p):
		return ast.Primitive(p, objects.List)

	# import

	@_("identifier_list COMMA identity")
	@_("identity")
	def identifier_list(self, p):
		idlist = getanyattr(p, 'identifier_list')
		if idlist:
			ret = [*idlist, p.identity]
		else:
			ret = [p.identity,]
		# print(ret)
		return ret

	@_("name_list COMMA name")
	@_("name")
	def name_list(self, p):
		idlist = getanyattr(p, 'name_list')
		if idlist:
			ret = [*idlist, p.name]
		else:
			ret = [p.name,]
		return ret

	@_("IMPORT BLOCK_OPEN name_list BLOCK_CLOSE FROM identity")
	@_("IMPORT BLOCK_OPEN MULTIPLY BLOCK_CLOSE FROM identity")
	def iport(self, p):
		return ast.Import(p)

	# types

	@_("identity BRACK_OPEN identifier_list BRACK_CLOSE")
	@_("identity")
	def typ(self, p):
		idlist = getanyattr(p, 'identifier_list')
		# print("typ", p.IDENTIFIER, idlist)
		if idlist is not None:
			ret = ast.TypeId(ast.Subscript(p.identity, idlist))
		else:
			ret = ast.TypeId(p.identity)
		# print(ret)
		return ret

	# functions

	@_("name COLON typ EQUALS expr")
	@_("name COLON typ")
	def param(self, p):
		return ast.Parameter(p.name, p.typ)

	@_("param_list COMMA param")
	@_("param")
	def param_list(self, p):
		l = getanyattr(p, 'param_list')
		if l is not None:
			return l + [p.param]
		else:
			return [p.param]

	@_("BLOCK_OPEN stmt_list BLOCK_CLOSE")
	@_("BLOCK_OPEN BLOCK_CLOSE")
	def block(self, p):
		return getattr(p, 'stmt_list', [])

	@_("FUN name PAREN_OPEN param_list PAREN_CLOSE block")
	@_("FUN name PAREN_OPEN param_list PAREN_CLOSE COLON typ block")
	@_("FUN name PAREN_OPEN PAREN_CLOSE block")
	@_("FUN name PAREN_OPEN PAREN_CLOSE COLON typ block")
	def func(self, p):
		return ast.Function(p)

	# function calls

	@_("arg_list COMMA expr")
	@_("expr")
	def arg_list(self, p):
		if len(p) == 3:
			return p.arg_list + [p.expr]
		return [p.expr]

	@_("identity PAREN_OPEN PAREN_CLOSE")
	@_("identity PAREN_OPEN arg_list PAREN_CLOSE")
	def func_call(self, p):
		fun = ast.FunctionCall(p)
		# print(fun)
		return fun

	@_("RETURN expr")
	@_("RETURN")
	def return_stmt(self, p):
		return ast.Return(getanyattr(p, 'expr'))

	@_("BREAK")
	def break_stmt(self, p):
		return ast.Break(p)

	@_("CONTINUE")
	def continue_stmt(self, p):
		return ast.Continue(p)

	# control flow

	@_("if_stmt")
	@_("if_stmt elseif_chain")
	@_("if_stmt elseif_chain else_stmt")
	@_("if_stmt else_stmt")
	def control(self, p):
		return ast.IfControl(p)

	@_("for_stmt")
	@_("try_catch_finally")
	def control(self, p):
		return p[0]

	@_("elseif_chain elseif_stmt")
	@_("elseif_stmt")
	def elseif_chain(self, p):
		if len(p) == 2:
			return [*p.elseif_chain, p.elseif_stmt]
		return [p.elseif_stmt]

	@_("IF PAREN_OPEN expr PAREN_CLOSE block")
	def if_stmt(self, p):
		return ast.If(p)

	@_("ELSEIF PAREN_OPEN expr PAREN_CLOSE block")
	def elseif_stmt(self, p):
		return ast.ElseIf(p)

	@_("ELSE block")
	def else_stmt(self, p):
		return ast.Else(p)

	@_("FOR PAREN_OPEN name IN expr PAREN_CLOSE block")
	def for_stmt(self, p):
		return ast.ForControl(p)

	@_("expr DQMARK expr")
	def expr(self, p):
		return ast.NilOrElse(p)

	@_("param_list ANON_CHECK expr %prec lambda")
	def lambda_expr(self, p):
		return ast.Lambda(p)

	@_("CATCH PAREN_OPEN name COLON typ PAREN_CLOSE block")
	def catch(self, p):
		return ast.Catch(p)

	@_("catch_list catch")
	@_("catch")
	def catch_list(self, p):
		if len(p) == 2:
			return [*p.catch_list, p.catch]
		return [p.catch]

	@_("TRY block catch_list")
	@_("TRY block FINALLY block")
	@_("TRY block catch_list FINALLY block")
	def try_catch_finally(self, p):
		return ast.TryControl(p)

	@_("THROW expr")
	def throw_stmt(self, p):
		return ast.Throw(p)

	def error(self, t):
		if not t:
			print("ERROR:-1: EOF encountered")
		else:
			# print(f"ERROR:{t.lineno}: unexpected {t.value!r}")
			self._error_list.append(copy.copy(t))

parser = VioletParser()
