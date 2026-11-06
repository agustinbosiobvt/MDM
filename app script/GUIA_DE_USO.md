# Guía de uso

Abre el enlace `/exec` con tu cuenta de buenavidatrading.com. El menú ofrece Inicio, Empresas, Clientes y Proveedores. Todos los usuarios BVT tienen los mismos permisos.

## Fichas

- Busca por código o nombre. El selector Activos/Retirados permite ver registros retirados. Las columnas con flechas se pueden ordenar; hay 50 filas por página.
- Pulsa una fila para abrirla. Usa Editar datos para cambiar su información y Añadir para crear direcciones o contactos.
- Los códigos se convierten a mayúsculas y no pueden repetirse entre los tres módulos, tampoco en registros retirados.
- La primera empresa es predeterminada. Haz otra predeterminada antes de retirar la actual.
- El primer contacto es principal. Hacer principal mueve la marca a otro contacto.
- Los códigos Amazon son pares padre/hijo del cliente. Un par activo solo puede estar asignado una vez.
- Retirar conserva el registro y su historial; Reactivar lo devuelve. Eliminar definitivamente exige retirar primero y escribir su código. Una empresa predeterminada o una ficha que haya tenido precios no se elimina.
- Si aparece un conflicto de versión, recarga la ficha antes de volver a guardar.

## Importar precios

1. Abre el cliente o proveedor y pulsa **Importar lista de precios**. Selecciona un `.xlsx` o `.csv` UTF-8 de hasta 20 MB. No se admiten `.xls` ni `.xlsm`.
2. Selecciona hoja, fila de cabecera y primera fila de datos. Déjalas vacías para detectar las filas. Si existe una plantilla de ese propietario, puedes seleccionarla. Revisa la muestra de 20 filas.
3. Mapea columnas por su letra. Un producto necesita EAN, UPC o ASIN. Para cada precio elige tipo y moneda fija, o la columna que contiene su moneda. Selecciona dimensiones como puerto o país si distinguen filas del mismo producto. Marca la confirmación de precios y monedas.
4. Espera la validación. Revisa líneas válidas, advertencias, rechazos, duplicados y recuento de precios por moneda. Completa nombre, moneda principal y fechas. Puedes guardar el mapeo con un nombre para reutilizarlo. Crea el borrador.

Los importes se guardan exactamente con cuatro decimales y conservan su propia moneda. La moneda principal de la lista no convierte ni sustituye las monedas de los precios. La app no usa los tipos de cambio que aparezcan en los archivos.

Los Excel con fórmulas deben haberse recalculado y guardado en Excel. La app conserva sus resultados guardados y retira las fórmulas de la copia temporal antes de convertirla a Google Sheets. Un resultado no guardado puede quedar vacío y debe revisarse en el informe.

## Revisar y activar

En la sección de precios puedes elegir una versión, buscar productos y filtrar por marca, categoría o estado. Cada importe muestra su moneda. La tabla tiene 50 líneas por página.

Editar permite cambiar solo marca y categoría. Los precios no se modifican. Para cambiar precios debes importar una nueva versión.

Los duplicados impiden activar. En un borrador usa Excluir en las líneas sobrantes; puedes verlas con el filtro Excluido y volver a incluirlas. Activar conserva el historial y vence las versiones activas de la misma moneda cuyos períodos se solapan.

Solo los borradores se retiran, escribiendo su nombre. Las versiones activas y vencidas se conservan. El historial muestra autor, fechas y revisiones.

No edites directamente las hojas ni los archivos de datos. Usa la app para que se apliquen las validaciones y quede registrado quién hizo cada cambio.
