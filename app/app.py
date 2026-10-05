from flask import Flask, jsonify, render_template, request
from mysql.connector import Error

from .db import get_connection
from.services import (
    process_payment,
    generate_invoice,
    register_event
)

app = Flask(__name__)

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/api/productos")
def productos():
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)

        cur.execute(
            """
                SELECT id_producto, nombre, descripcion, precio, stock, estado
                FROM productos
                WHERE estado = TRUE
                ORDER BY id_producto
            """
        )

        rows = cur.fetchall()

        for row in rows:
            row["precio"] = float(row["precio"])
            row["estado"] = bool(row["estado"])

        return jsonify(rows)
    
    except Error as e:
        return jsonify({
            "error": "No fue posible consultar los productos.",
            "detalle": str(e)
        }), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@app.post("/api/comprar")
def comprar():
    """
    Procesa una compra completa utilizando una única
    transacción MySQL.
    """

    conn = None
    cur = None

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                "error": "Debe enviar información de la compra."
            }), 400

        cliente_id = data.get("cliente_id")
        producto_id = data.get("producto_id")
        cantidad = data.get("cantidad")
        fail_payment = bool(data.get("fail_payment", False))
        fail_invoice = bool(data.get("fail_invoice", False))

        idempotency_key = request.headers.get("Idempotency-Key")

        # Validaciones
        if not cliente_id:
            return jsonify({
                "error": "cliente_id es obligatorio."
            }), 400 

        if not producto_id:
            return jsonify({
                "error": "producto_id es obligatorio."
            }), 400 

        if not cantidad or cantidad <= 0:
            return jsonify({
                "error": "La cantidad debe ser mayor que cero."
            }), 400

        if not idempotency_key:
            return jsonify({
                "error": "El header Idempotency-Key es obligatorio."
            }), 400

        # Conexión
        conn = get_connection()
        cur = conn.cursor(dictionary=True)

        # Idempotencia
        cur.execute(
            """
            SELECT id_compra, estado, total, mensaje
            FROM compras
            WHERE idempotency_key = %s
            """,
            (idempotency_key,)
        )

        existing_purchase = cur.fetchone()

        if existing_purchase:
            return jsonify({
                "mensaje": "La solicitud ya fue procesada",
                "id_compra": existing_purchase["id_compra"],
                "estado": existing_purchase["estado"],
                "total": float(existing_purchase["total"]),
                "resultado_anterior": True                
            }), 200

        conn.start_transaction()

        cur.execute(
            """
            SELECT id_producto, nombre, descripcion, precio, stock
            FROM productos
            WHERE id_producto = %s AND estado = TRUE
            FOR UPDATE
            """,
            (producto_id,)
        ) 

        product = cur.fetchone()

        if not product:
            raise ValueError("El producto no existe o no está disponible.")

        # Validar stock
        if product["stock"] < cantidad:
            raise ValueError("No hay suficiente stock disponible.")

        precio_unitario = float(product["precio"])
        subtotal = precio_unitario * cantidad

        # Actualizar inventario
        cur.execute(
            """
            UPDATE productos
            SET stock = stock - %s
            WHERE id_producto = %s
                AND stock >= %s
            """,
            (cantidad, producto_id, cantidad)
        )

        if cur.rowcount != 1:
            raise ValueError("No fue posible actualizar el inventario.")

        # Registrar compra
        cur.execute(
            """
            INSERT INTO compras (id_cliente, total, estado, idempotency_key, mensaje)
            VALUES (%s, %s, 'PENDIENTE', %s, %s)
            """,
            (cliente_id, subtotal, idempotency_key, "Compra en proceso")
        )

        purchase_id = cur.lastrowid

        # Registar detalle
        cur.execute(
            """
            INSERT INTO detalle_compra (id_compra, id_producto, cantidad, precio_unitario)
            VALUES (%s, %s, %s, %s)
            """,
            (purchase_id, producto_id, cantidad, precio_unitario)
        )

        register_event(cur, purchase_id, "COMPRAS", "COMPRA_CREADA", f"Producto={purchase_id}, cantidad={cantidad}")

        # Procesar pago
        payment_ok = process_payment(cur, purchase_id, fail=fail_payment)

        if not payment_ok:
            register_event(cur, purchase_id, "PAGOS", "PAGO_RECHAZADO", f"Producto={purchase_id}, cantidad={cantidad}")
            raise ValueError("El pago fue rechazado.")

        register_event(cur, purchase_id, "PAGOS", "PAGO_APROBADO", f"Pago-{purchase_id}")

        # Generar factura
        invoice = generate_invoice(cur, purchase_id, subtotal, fail=fail_invoice)

        register_event(cur, purchase_id, "FACTURACION", "FACTURA_GENERADA", f"Total={invoice['total']}")

        # Confirmar compra
        cur.execute(
            """
            UPDATE compras
            SET estado = 'CONFIRMADA', mensaje = 'Compra procesada correctamente'
            WHERE id_compra = %s
            """,
            (purchase_id,)
        )

        conn.commit()

        return jsonify({
            "mensaje": "Compra confirmada",
            "id_compra": purchase_id,
            "estado": "CONFIRMADA",
            "producto": product["nombre"],
            "cantidad": cantidad,
            "subtotal": subtotal,
            "total": invoice["total"],
            "idempotency_key": idempotency_key,
        }), 201

    except ValueError as error:
        if conn:
            conn.rollback()

        return jsonify({
            "mensaje": "Compra rechazada",
            "error": str(error)
        }), 400

    except RuntimeError as error:
        if conn:
            conn.rollback()

        return jsonify({
            "mensaje": "La compra no pudo ser completada",
            "error": str(error),
            "rollback": True
        }), 400

    except Error as error:
        if conn:
            conn.rollback()

        return jsonify({
            "mensaje": "Error en la base de datos",
            "error": str(error),
            "rollback": True
        }), 500

    except Exception as error:
        if conn:
            conn.rollback()

        return jsonify({
            "mensaje": "Error inesperado",
            "error": str(error),
            "rollback": True
        }), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()