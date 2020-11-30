from .objects import *

class Panic(BaseException):
	pass

class StatementError(Exception):
	def __init__(self, stmt, msg):
		super().__init__(msg)
		self.stmt = stmt

class _Exit(Exception):
	pass

class ReturnExit(_Exit):
	pass

class BreakExit(_Exit):
	pass

class ContinueExit(_Exit):
	pass

class RuntimeException(Exception, Object):
	def __init__(self, message):
		self.message = message
		self.stmt = None

	def __repr__(self):
		return f"<Exception {self.__class__.__name__} message={self.message}>"

	def _operator_cast(self, typ):
		if typ is String:
			return String(repr(self))
		elif typ is Boolean:
			return Boolean(True)

		else:
			raise Exception(f"Cannot cast {self.__class__.__name__!r} to {typ.__name__!r}")