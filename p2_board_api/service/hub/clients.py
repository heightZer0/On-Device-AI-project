"""실제 HTTP 클라이언트(P3 /speak, P4 LLM 서버). 발화 원문은 로그에 남기지 않는다."""
import httpx


class LLMUnavailable(Exception): ...
class LLMTimeout(Exception): ...


class HttpSpeakClient:
    def __init__(self, base_url, timeout):
        self.base, self.timeout = base_url.rstrip("/"), timeout

    def _post(self, path, body):
        httpx.post(self.base + path, json=body, timeout=self.timeout).raise_for_status()

    def speak(self, text, kind, volume):
        self._post("/speak", {"text": text, "kind": kind, "volume": max(0.0, min(1.0, float(volume)))})

    def warmup(self, texts):
        self._post("/speak/warmup", {"texts": texts})

    def set_mic(self, enabled):
        self._post("/mic", {"enabled": enabled})

    def set_settings(self, settings):
        self._post("/settings", {"tts_volume": settings["tts_volume"], "tts_speed": settings["tts_speed"]})

    def state(self):
        r = httpx.get(self.base + "/speak/state", timeout=1.0)
        r.raise_for_status()
        return r.json()


class HttpLLMClient:
    def __init__(self, url, model, timeout, system_prompt=""):
        self.url, self.model, self.timeout = url, model, timeout
        self.system_prompt = system_prompt

    def complete(self, utterance):
        try:
            messages = []
            if self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})
            messages.append({"role": "user", "content": utterance})
            r = httpx.post(self.url, timeout=self.timeout, json={
                "model": self.model, "stream": False,
                "temperature": 0, "top_k": 1, "enable_thinking": False, "max_tokens": 64,
                "messages": messages})
        except httpx.TimeoutException as e:
            raise LLMTimeout() from e
        except httpx.HTTPError as e:
            raise LLMUnavailable() from e
        if r.status_code >= 500:
            raise LLMUnavailable()
        if r.status_code >= 400:
            raise LLMUnavailable()
        try:
            content = r.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise LLMUnavailable() from e
        if not isinstance(content, str) or not content.strip():
            raise LLMUnavailable()
        return content   # 보드 출력 원문을 파서에 전달한다.

    def health(self):
        base = self.url.split("/v1/")[0]
        try:
            r = httpx.get(base + "/health", timeout=1.0)
            if r.status_code == 200:
                return "ready"
            # rkllm-board exposes /v1/models but does not implement /health.
            r = httpx.get(base + "/v1/models", timeout=1.0)
            return "ready" if r.status_code == 200 else "error"
        except httpx.HTTPError:
            try:
                r = httpx.get(base + "/v1/models", timeout=1.0)
                return "ready" if r.status_code == 200 else "error"
            except httpx.HTTPError:
                return "error"
