class BusinessRuleError(ValueError):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule
