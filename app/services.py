from mysql.connector import Error

def process_payment(cursor, compra_id, fail=False):
    """
    Simula el procesamiento de un pago.

    Si fail=True, el pago se marca como rechazado y devuelve falso.
    Si fail=False, el pago se marca como aprobado y devuelve verdadero.        
    """

    if fail:
        cursor.execute(
            """
            INSERT INTO pagos (id_compra, estado, referencia)
            VALUES (%s, 'RECHAZADO', %s)
            """,
            (compra_id, f"PAGO-FALLIDO-{compra_id}")
        )

        return False

    cursor.execute(
        """
        INSERT INTO pagos (id_compra, estado, referencia)
        VALUES (%s, 'APROBADO', %s)
        """,
        (compra_id, f"PAGO-EXITOSO-{compra_id}")
    )

    return True

def generate_invoice(cursor, compra_id, subtotal, fail=False):
    """
    Genera la factura asociada a una compra.
    """

    if fail:
        raise RuntimeError("Error al generar la factura.")

    impuestos = subtotal * 0.19  # 19% de impuestos
    total = subtotal + impuestos

    cursor.execute(
        """
        INSERT INTO facturas (id_compra, subtotal, impuestos, total, estado)
        VALUES (%s, %s, %s, %s, 'GENERADA')
        """,
        (compra_id, subtotal, impuestos, total)
    )

    return {
        "subtotal": (subtotal),
        "impuestos": (impuestos),
        "total": (total)
    }

def register_event(cursor, compra_id, servicio, evento, detalle=None):
    """
    Registra un evento del proceso transaccional.
    """

    cursor.execute(
        """
        INSERT INTO eventos (id_compra, servicio, evento, detalle)
        VALUES (%s, %s, %s, %s)
        """,
        (compra_id, servicio, evento, detalle)
    )