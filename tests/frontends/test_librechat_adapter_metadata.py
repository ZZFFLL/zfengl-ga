import unittest


class MetadataTestCase(unittest.TestCase):
    def metadata_module(self):
        try:
            from frontends.librechat_adapter import metadata
        except ImportError as exc:
            self.fail(f"metadata module should be importable: {exc}")
        return metadata

    def test_body_values_take_precedence_over_headers(self):
        metadata = self.metadata_module()

        meta = metadata.extract_request_meta(
            {
                "conversationId": "body-conv",
                "parentMessageId": "body-parent",
                "user": "body-user",
                "request_id": "body-request",
            },
            {
                "x-ga-librechat-conversation-id": "header-conv",
                "x-ga-librechat-parent-message-id": "header-parent",
                "x-ga-librechat-user-id": "header-user",
            },
        )

        self.assertEqual(meta.conversation_id, "body-conv")
        self.assertEqual(meta.parent_message_id, "body-parent")
        self.assertEqual(meta.user_id, "body-user")
        self.assertEqual(meta.request_id, "body-request")
        self.assertEqual(meta.source, "body")

    def test_headers_are_used_when_body_metadata_is_missing(self):
        metadata = self.metadata_module()

        meta = metadata.extract_request_meta(
            {},
            {
                "x-ga-librechat-conversation-id": "header-conv",
                "x-ga-librechat-parent-message-id": "header-parent",
                "x-ga-librechat-user-id": "header-user",
            },
        )

        self.assertEqual(meta.conversation_id, "header-conv")
        self.assertEqual(meta.parent_message_id, "header-parent")
        self.assertEqual(meta.user_id, "header-user")
        self.assertEqual(meta.source, "header")

    def test_empty_null_undefined_and_template_values_fall_back(self):
        metadata = self.metadata_module()

        meta = metadata.extract_request_meta(
            {
                "conversationId": "{{conversationId}}",
                "parentMessageId": "undefined",
                "user": {"id": None},
            },
            {
                "x-ga-librechat-conversation-id": "",
                "x-ga-librechat-parent-message-id": "null",
                "x-ga-librechat-user-id": "{{user.id}}",
            },
        )

        self.assertEqual(meta.conversation_id, "default-conversation")
        self.assertEqual(meta.parent_message_id, "")
        self.assertEqual(meta.user_id, "local-single-user")
        self.assertEqual(meta.source, "fallback")

    def test_conversation_key_uses_user_and_conversation(self):
        metadata = self.metadata_module()
        meta = metadata.LibreChatRequestMeta(
            conversation_id="conv-1",
            parent_message_id="parent-1",
            user_id="user-1",
            request_id="request-1",
            source="librechat",
        )

        self.assertEqual(metadata.conversation_key(meta), "user-1:conv-1")


if __name__ == "__main__":
    unittest.main()
