# Strict text routing

Status: current

An upstream text response can echo an arbitrary requested model name. A successful
response alone therefore does not establish that the requested model was selected.
For API-router deployments, two independent opt-in settings enforce local routing
requirements without changing the default compatibility behaviour.

## Enable through the configuration owner

Run the following Python in the application's environment, with its normal
bootstrap authentication configuration available. `ConfigStore.update` writes to
the Application Database; editing `config.json` does not change these settings.

```python
from services.config import config

config.update({
    "model_catalog": {"chat_models": ["auto", "your-verified-model"]},
    "text_validate_model_catalog": True,
    "text_require_authenticated_account": True,
})
```

Replace the example model with an identifier verified for the intended upstream
account. The model catalog is an administrator-maintained allowlist, not an
automatic account-capability discovery mechanism. Preserve any existing image
catalog settings when replacing the `model_catalog` object.

With catalog validation enabled, text Chat Completions, Responses, and Messages accept only
entries in the same chat catalog exposed by `/v1/models` and the console. An
explicit unknown model returns HTTP 400 before inference or cache access. A
missing or blank model uses the catalog's default. `auto` is accepted only when
included in the catalog; it deliberately delegates model selection upstream.

With authenticated-account enforcement enabled, text inference returns HTTP 503
when no eligible access token is available, instead of creating an anonymous
backend. Existing successful cache entries retain their normal cache behaviour.
This setting does not validate the subscription tier or establish engine identity.

Both settings default to false. Disable either independently with
`config.update({"text_validate_model_catalog": False})` or
`config.update({"text_require_authenticated_account": False})`. The existing
repository refresh mechanism makes changes visible to running workers.

These policies apply to text inference. Image generation keeps its existing
account pool and image-model routing rules.
