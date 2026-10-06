let selectedProduct = null;

// Carga los productos desde Flask
async function cargarProductos() {
    const response = await fetch('/api/productos');

    if (!response.ok)
        throw new Error('No fue posible cargar los productos.');
    
    const productos = await response.json();
    const container = document.getElementById('products');
    
    container.innerHTML = productos.map(producto => `
        <article class="product">
            <h3>${producto.nombre}</h3>
            <p>${producto.descripcion}</p>
            <strong>Precio: $${producto.precio.toLocaleString('es-CO')}</strong>
            <p>Stock: ${producto.stock}</p>
            <button 
                onclick="seleccionarProducto(${producto.id_producto})"
                ${producto.stock <= 0 ? 'disabled' : ''}
            >
                Seleccionar
            </button>
        </article>
    `).join('');
}

async function seleccionarProducto(productoId) {
    const response = await fetch(`/api/productos`);
    const productos = await response.json();

    selectedProduct = productos.find(producto => producto.id_producto === productoId);

    mostrarResultado({
        mensaje: "Producto seleccionado.",
        producto: selectedProduct.nombre
    });
}

// Generar clave de idempotencia única
function generarIdempotencyKey() {
    return "ORD-" + crypto.randomUUID();
}

// Ejecutar la compra del producto seleccionado
async function comprar() {
    const resultElement = document.getElementById('result');

    if (!selectedProduct) {
        mostrarResultado({
            mensaje: "No se ha seleccionado ningún producto."
        });
        return;
    }

    const clienteId = Number(document.getElementById('client').value);
    const quantity = Number(document.getElementById('quantity').value);
    const failPayment = document.getElementById('failPayment').checked;
    const failInvoice = document.getElementById('failInvoice').checked;

    if (quantity <= 0) {
        mostrarResultado({
            mensaje: "Cantidad inválida. Debe ser mayor a 0."
        });
        return;
    }

    const idempotencyKey = generarIdempotencyKey();

    try {
        resultElement.textContent = "Procesando la compra...";
        const response = await fetch('/api/comprar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Idempotency-Key': idempotencyKey
            },
            body: JSON.stringify({
                cliente_id: clienteId,
                producto_id: selectedProduct.id_producto,
                cantidad: quantity,
                fail_payment: failPayment,
                fail_invoice: failInvoice,                
            })
        });    

        const result = await response.json();

        mostrarResultado(result);

        await cargarProductos();

    } catch (error) {
        mostrarResultado({
            error: error.message
        });
    }
}

// Mostrar resultado en pantalla
function mostrarResultado(data) {
    document.getElementById("result")
        .textContent = JSON.stringify(data, null, 2);
}

document.getElementById("buyButton").addEventListener("click", comprar);

cargarProductos()
    .catch(error => {
        mostrarResultado({
            error: error.message
        });
    });