"""SDK-independent response errors with safe, fixed diagnostic codes."""


class EmptyModelResponse(ValueError):
    def __init__(self, code: str = "empty_text_response"):
        if code not in {"empty_text_response", "empty_structured_output"}:
            raise ValueError("invalid empty response code")
        self.code = code
        super().__init__(code)
