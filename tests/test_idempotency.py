import unittest
from unittest.mock import MagicMock, patch

from app.app import app


class IdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.purchase_data = {
            "cliente_id": 1,
            "producto_id": 2,
            "cantidad": 1,
        }

    def test_repeated_request_with_same_key_returns_original_purchase(self):
        first_connection = MagicMock()
        first_cursor = MagicMock()
        first_cursor.fetchone.side_effect = [
            None,
            {
                "id_producto": 2,
                "nombre": "Mouse Inalámbrico",
                "descripcion": "Mouse óptico.",
                "precio": 89900,
                "stock": 5,
            },
        ]
        first_cursor.lastrowid = 42
        first_cursor.rowcount = 1
        first_connection.cursor.return_value = first_cursor

        second_connection = MagicMock()
        second_cursor = MagicMock()
        second_cursor.fetchone.return_value = {
            "id_compra": 42,
            "estado": "CONFIRMADA",
            "total": 89900,
            "mensaje": "Compra procesada correctamente",
        }
        second_connection.cursor.return_value = second_cursor

        with patch(
            "app.app.get_connection",
            side_effect=[first_connection, second_connection],
        ) as get_connection:
            first_response = self.client.post(
                "/api/comprar",
                json=self.purchase_data,
                headers={"Idempotency-Key": "test-order-42"},
            )
            second_response = self.client.post(
                "/api/comprar",
                json={
                    **self.purchase_data,
                    "producto_id": 3,
                    "cantidad": 2,
                },
                headers={"Idempotency-Key": "test-order-42"},
            )

        first_result = first_response.get_json()
        second_result = second_response.get_json()

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(first_result["id_compra"], 42)
        self.assertEqual(first_result["estado"], "CONFIRMADA")

        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_result["id_compra"], first_result["id_compra"])
        self.assertEqual(second_result["estado"], first_result["estado"])
        self.assertTrue(second_result["resultado_anterior"])

        purchase_inserts = [
            args[0]
            for args, _ in first_cursor.execute.call_args_list
            if "INSERT INTO compras" in args[0]
        ]
        stock_updates = [
            args[0]
            for args, _ in first_cursor.execute.call_args_list
            if "UPDATE productos" in args[0]
        ]
        self.assertEqual(len(purchase_inserts), 1)
        self.assertEqual(len(stock_updates), 1)
        self.assertEqual(second_cursor.execute.call_count, 1)
        duplicate_lookup, duplicate_params = second_cursor.execute.call_args.args
        self.assertIn("WHERE idempotency_key = %s", duplicate_lookup)
        self.assertEqual(duplicate_params, ("test-order-42",))
        first_connection.commit.assert_called_once()
        first_connection.start_transaction.assert_called_once()
        second_connection.start_transaction.assert_not_called()
        self.assertEqual(get_connection.call_count, 2)

    def test_request_without_idempotency_key_is_rejected(self):
        with patch("app.app.get_connection") as get_connection:
            response = self.client.post(
                "/api/comprar",
                json=self.purchase_data,
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "El header Idempotency-Key es obligatorio.",
        )
        get_connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()