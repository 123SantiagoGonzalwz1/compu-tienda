from flask import Flask, jsonify, render_template
from .db import get_connection

app = Flask(__name__)

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/api/productos")
def productos():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id_producto, nombre, descripcion, precio, stock, estado "
        "FROM productos WHERE estado = TRUE ORDER BY id_producto"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    for row in rows:
        row["precio"] = float(row["precio"])
        row["estado"] = bool(row["estado"])
    return jsonify(rows)