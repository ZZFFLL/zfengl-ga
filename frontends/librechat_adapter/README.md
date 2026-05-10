# GenericAgent LibreChat Adapter

This module exposes GenericAgent through a small OpenAI-compatible HTTP API for LibreChat custom endpoints.

## Start

```powershell
$env:GA_API_KEY='local-ga-dev-key'
py -3 -m frontends.librechat_adapter.server --host 127.0.0.1 --port 18601
```

## LibreChat Config

```yaml
endpoints:
  custom:
    - name: 'ga'
      apiKey: '${GA_API_KEY}'
      baseURL: 'http://127.0.0.1:18601/v1'
      models:
        default: ['generic-agent']
        fetch: false
      titleConvo: false
      modelDisplayLabel: 'GenericAgent'
      dropParams: ['stop', 'frequency_penalty', 'presence_penalty']
      headers:
        x-ga-librechat-conversation-id: '{{LIBRECHAT_BODY_CONVERSATIONID}}'
        x-ga-librechat-parent-message-id: '{{LIBRECHAT_BODY_PARENTMESSAGEID}}'
        x-ga-librechat-user-id: '{{LIBRECHAT_USER_ID}}'
```

Verify the placeholder names in the current LibreChat build before enabling conversation isolation. The adapter falls back to a local single-user conversation when metadata is missing.

## Endpoints

```powershell
curl.exe http://127.0.0.1:18601/health
curl.exe http://127.0.0.1:18601/v1/models -H "Authorization: Bearer local-ga-dev-key"
curl.exe http://127.0.0.1:18601/v1/ga/sessions -H "Authorization: Bearer local-ga-dev-key"
curl.exe -N http://127.0.0.1:18601/v1/chat/completions -H "Authorization: Bearer local-ga-dev-key" -H "Content-Type: application/json" -d "{\"model\":\"generic-agent\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}]}"
```

## First-Phase Limits

- One GenericAgent runtime is active at a time.
- No SQLite state store yet.
- No attachments or image forwarding yet.
- Conversation continuity after refresh or adapter restart comes from LibreChat `messages`.
- GA native sessions are exposed through read-only `/v1/ga/sessions` endpoints; restore is a later controlled operation.
