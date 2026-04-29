import json
import unittest


class ProtocolTestCase(unittest.TestCase):
    def protocol_module(self):
        try:
            from frontends.librechat_adapter import protocol
        except ImportError as exc:
            self.fail(f"protocol module should be importable: {exc}")
        return protocol

    def test_parse_chat_request_requires_generic_agent_model(self):
        protocol = self.protocol_module()

        with self.assertRaises(protocol.AdapterError) as caught:
            protocol.parse_chat_request(
                {"model": "other-model", "messages": [{"role": "user", "content": "hi"}]}
            )

        self.assertEqual(caught.exception.code, "invalid_model")
        self.assertEqual(caught.exception.status, 400)

    def test_parse_chat_request_requires_non_empty_messages(self):
        protocol = self.protocol_module()

        with self.assertRaises(protocol.AdapterError) as caught:
            protocol.parse_chat_request({"model": "generic-agent", "messages": []})

        self.assertEqual(caught.exception.code, "invalid_messages")

    def test_parse_chat_request_normalizes_string_and_text_part_content(self):
        protocol = self.protocol_module()

        request = protocol.parse_chat_request(
            {
                "model": "generic-agent",
                "stream": True,
                "user": "user-1",
                "conversation_id": "conv-1",
                "parent_message_id": "parent-1",
                "messages": [
                    {"role": "system", "content": "You are helpful."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "hello"},
                            {"type": "image_url", "image_url": {"url": "ignored"}},
                            {"text": "world"},
                        ],
                    },
                ],
            }
        )

        self.assertEqual(request.model, "generic-agent")
        self.assertTrue(request.stream)
        self.assertEqual(request.user, "user-1")
        self.assertEqual(request.conversation_id, "conv-1")
        self.assertEqual(request.parent_message_id, "parent-1")
        self.assertEqual(
            request.messages,
            [
                protocol.NormalizedMessage(role="system", content="You are helpful."),
                protocol.NormalizedMessage(role="user", content="hello\nworld"),
            ],
        )

    def test_latest_user_text_returns_last_user_message(self):
        protocol = self.protocol_module()
        messages = [
            protocol.NormalizedMessage("user", "first"),
            protocol.NormalizedMessage("assistant", "middle"),
            protocol.NormalizedMessage("user", "latest"),
        ]

        self.assertEqual(protocol.latest_user_text(messages), "latest")

    def test_build_prompt_can_include_or_exclude_history(self):
        protocol = self.protocol_module()
        messages = [
            protocol.NormalizedMessage("system", "policy"),
            protocol.NormalizedMessage("user", "first question"),
            protocol.NormalizedMessage("assistant", "first answer"),
            protocol.NormalizedMessage("user", "second question"),
        ]

        self.assertEqual(
            protocol.build_prompt_from_messages(messages, include_history=False),
            "second question",
        )
        prompt = protocol.build_prompt_from_messages(messages, include_history=True)
        self.assertIn("Conversation History:", prompt)
        self.assertIn("system: policy", prompt)
        self.assertIn("assistant: first answer", prompt)
        self.assertIn("Current User Message:", prompt)
        self.assertTrue(prompt.endswith("second question"))

    def test_build_prompt_trims_history_to_max_context_chars(self):
        protocol = self.protocol_module()
        messages = [
            protocol.NormalizedMessage("user", "a" * 20),
            protocol.NormalizedMessage("assistant", "b" * 20),
            protocol.NormalizedMessage("user", "current"),
        ]

        prompt = protocol.build_prompt_from_messages(
            messages, include_history=True, max_context_chars=45
        )

        self.assertLessEqual(len(prompt), 45)
        self.assertTrue(prompt.endswith("current"))

    def test_completion_response_sse_chunk_and_error_payload_are_openai_shaped(self):
        protocol = self.protocol_module()

        completion = protocol.make_completion_response(
            content="answer",
            model="generic-agent",
            request_id="chatcmpl-1",
            created=123,
        )
        self.assertEqual(completion["id"], "chatcmpl-1")
        self.assertEqual(completion["object"], "chat.completion")
        self.assertEqual(completion["choices"][0]["message"]["content"], "answer")

        chunk = protocol.make_sse_chunk(
            request_id="chatcmpl-1",
            model="generic-agent",
            delta={"content": "a"},
            finish_reason=None,
            created=123,
        )
        self.assertEqual(chunk["object"], "chat.completion.chunk")
        self.assertEqual(chunk["choices"][0]["delta"], {"content": "a"})

        error = protocol.make_error_payload("bad_request", "Nope")
        self.assertEqual(error["error"]["code"], "bad_request")
        self.assertEqual(error["error"]["message"], "Nope")
        self.assertEqual(error["error"]["type"], "invalid_request_error")
        json.dumps(error)


if __name__ == "__main__":
    unittest.main()
