new_chat_members_update = {
    "update_id": 86439805,
    "message": {
        "message_id": 846,
        "from": {
            "id": 1234567890,
            "is_bot": False,
            "first_name": "John Doe",
            "username": "johndoe",
            "language_code": "en",
        },
        "chat": {"id": -1003765868758, "title": "Test bots", "username": "testBot11223", "type": "supergroup"},
        "date": 1775076443,
        "new_chat_participant": {
            "id": 6204077458,
            "is_bot": False,
            "first_name": "Jane Doe",
            "username": "janedoe",
            "language_code": "en",
        },
        "new_chat_member": {
            "id": 6204077458,
            "is_bot": False,
            "first_name": "John Doe",
            "username": "johndoe",
            "language_code": "en",
        },
        "new_chat_members": [
            {
                "id": 1234567890,
                "is_bot": False,
                "first_name": "Jane Doe",
                "username": "janedoe",
                "language_code": "en",
            }
        ],
    },
}

new_chat_member_callback_query_update = {
    "update_id": 86439808,
    "callback_query": {
        "id": "8199565710514543348",
        "from": {
            "id": 1234567890,
            "is_bot": False,
            "first_name": "John Doe",
            "username": "johndoe",
            "language_code": "en",
        },
        "message": {
            "message_id": 850,
            "from": {
                "id": 6204077458,
                "is_bot": False,
                "first_name": "John Doe",
                "username": "johndoe",
                "language_code": "en",
            },
            "chat": {"id": -1003765868758, "title": "Test bots", "username": "testBot11223", "type": "supergroup"},
            "date": 1775076555,
            "message_thread_id": 849,
            "reply_to_message": {
                "message_id": 849,
                "from": {
                    "id": 6204077458,
                    "is_bot": False,
                    "first_name": "Jane Doe",
                    "username": "janedoe",
                    "language_code": "en",
                },
                "chat": {"id": -1003765868758, "title": "Test bots", "username": "testBot11223", "type": "supergroup"},
                "date": 1775076555,
                "new_chat_participant": {
                    "id": 1234567890,
                    "is_bot": False,
                    "first_name": "Jane Doe",
                    "username": "janedoe",
                    "language_code": "en",
                },
                "new_chat_member": {
                    "id": 1234567890,
                    "is_bot": False,
                    "first_name": "John Doe",
                    "username": "johndoe",
                    "language_code": "en",
                },
                "new_chat_members": [
                    {
                        "id": 1234567890,
                        "is_bot": False,
                        "first_name": "Jane Doe",
                        "username": "janedoe",
                        "language_code": "en",
                    }
                ],
            },
            "text": "👋 Welcome X Ray!\n\nТоп сапасын сақтау үшін, бот емес екеніңізді растаңыз.\n\n⏳ Уақыт шектеулі: 60 секунд\n\n(Уақыт өтсе, автоматты түрде шығарыласыз)",  # noqa: E501
            "entities": [
                {
                    "offset": 11,
                    "length": 5,
                    "type": "text_mention",
                    "user": {
                        "id": 1234567890,
                        "is_bot": False,
                        "first_name": "Jane Doe",
                        "username": "janedoe",
                        "language_code": "en",
                    },
                },
                {"offset": 77, "length": 25, "type": "bold"},
            ],
            "reply_markup": {
                "inline_keyboard": [[{"text": "Мен адаммын / I am human", "callback_data": "verify_1234567890"}]]
            },
        },
        "chat_instance": "4848765629685820695",
        "data": "verify_1234567890",
    },
}
