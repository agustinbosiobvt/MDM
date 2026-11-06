# Instalación de BVT MDM

## 1. Elige la cuenta propietaria

Usa una cuenta de Google Workspace **@buenavidatrading.com** con continuidad en la empresa. Esa cuenta será propietaria del proyecto, la carpeta de datos y las copias. Abre Google Drive y Apps Script con ella. No hace falta configurar el cliente OAuth del proyecto anterior.

La aplicación se ejecuta con los permisos del propietario y solo acepta correos del dominio BVT. **Cualquier persona del dominio con el enlace puede consultar, editar y eliminar fichas con las confirmaciones indicadas.** Es el modelo solicitado en el plan de migración.

## 2. Sube y convierte la base

1. Sube `MDM_Data.xlsx` a Google Drive.
2. Ábrelo con Hojas de cálculo de Google.
3. Usa **Archivo → Guardar como Hojas de cálculo de Google**. Debe quedar un archivo nativo de Google Sheets, no un Excel abierto en modo de compatibilidad.
4. Ponle el nombre `MDM_Data`.
5. Copia su ID: en `https://docs.google.com/spreadsheets/d/ID_DEL_ARCHIVO/edit`, es el texto entre `/d/` y `/edit`.
6. Mantén el acceso general **Restringido** y no lo compartas con los usuarios de la aplicación.

No cambies los nombres de hojas ni la primera fila. Las hojas de negocio vacías son correctas: PostgreSQL no tenía registros de negocio al exportar. La hoja `AuditLog` contiene 23 eventos y `Lookups`, 427 filas de catálogo.

## 3. Crea el proyecto y copia los archivos

1. Abre [Google Apps Script](https://script.google.com/) → **Nuevo proyecto**. Nombre: `BVT MDM`.
2. En **Configuración del proyecto**, activa **Mostrar el archivo de manifiesto appsscript.json en el editor**.
3. Abre `appsscript.json` y reemplaza su contenido con el entregado.
4. Reemplaza `Code.gs` y crea el resto de archivos con **+ → Secuencia de comandos** o **+ → HTML**. En el editor escribe el nombre sin la extensión; Google la agrega.

**Secuencias de comandos:**

```text
Schema.gs
Lookups.gs
Code.gs
Db.gs
Validation.gs
Setup.gs
Company.gs
Parties.gs
PriceLists.gs
Import.gs
Backup.gs
Tests.gs
```

**HTML:**

```text
Index.html
Styles.html
App.html
Lists.html
Forms.html
ImportWizard.html
```

El orden de creación no importa. Copia cada archivo entero, incluidos `<script>` o `<style>` en los HTML. No crees archivos para los Excel, documentos ni JSON de la carpeta `migracion`.

5. En **Servicios**, comprueba que figure **Drive API v3**, identificador `Drive`. El manifiesto ya lo declara. Si usas un proyecto estándar de Google Cloud, habilita también **Google Drive API** en su consola.

**Si aparece v2:** abre `appsscript.json` y, dentro de `dependencies.enabledAdvancedServices`, cambia la entrada del servicio con `serviceId: "drive"` para que tenga `"version": "v3"` y `"userSymbol": "Drive"`. Guarda y recarga el editor. Debe haber una sola entrada para ese servicio; no agregues otra con el mismo identificador. También puedes volver a pegar el manifiesto completo entregado si todavía no hiciste cambios propios. Selecciona **Drive API**: **Drive Activity API** es otro servicio y su versión v2 no sirve para esta aplicación. Google permite habilitar v3 directamente desde el manifiesto: [instrucciones oficiales](https://developers.google.com/apps-script/guides/services/advanced).

## 4. Conecta el Excel convertido

En **Configuración del proyecto → Propiedades de la secuencia de comandos → Añadir propiedad**, crea:

| Propiedad | Valor |
| --- | --- |
| `MDM_DATA_ID` | ID del archivo nativo que convertiste en el paso 2 |

No pongas la URL completa. No pongas el ID de la carpeta ni el del archivo `.xlsx` original.

## 5. Ejecuta la instalación

1. Guarda el proyecto.
2. En el selector de funciones, elige **`setup`** y pulsa **Ejecutar**.
3. Autoriza los permisos con la cuenta propietaria. Sheets permite leer/escribir datos; Drive permite conservar fuentes y copias; el correo identifica al autor; los activadores permiten la copia nocturna.
4. `setup` crea la carpeta privada `MDM Data`, mueve allí la base y crea:

```text
MDM Data/
  MDM_Data                  ← Google Sheets, base principal
  PriceLists/               ← un Google Sheets por versión de precios
    Sources/                ← Excel/CSV originales
  Import staging/           ← conversiones y validaciones temporales
  Backups/                  ← copias de base y versiones de líneas
```

5. Ejecuta **`runTests`**: el registro debe decir **27 comprobaciones puras**. No crea ni borra fichas de negocio.
6. Ejecuta **`installBackupTrigger`**. Se crea un único activador nocturno entre las 02:00 y las 03:00, hora de Madrid. Volver a ejecutarlo reemplaza el anterior.
7. Ejecuta **`nightlyBackup`** una vez desde el editor para verificar permisos y generar la primera copia.

`setup` es reutilizable: no borra datos ni recrea una base que ya esté configurada. Si olvidaste `MDM_DATA_ID`, crea una base nueva vacía con los catálogos; no importará automáticamente el historial del Excel. Para conservarlo, configura el ID correcto antes de la primera ejecución. Si ya ejecutaste la instalación con una base equivocada, cambia solo `MDM_DATA_ID` por el correcto y ejecuta `setup` otra vez.

## 6. Publica la aplicación

1. **Implementar → Nueva implementación**.
2. Tipo: **Aplicación web**.
3. **Ejecutar como: Yo**, la cuenta propietaria.
4. **Quién tiene acceso: cualquier usuario de buenavidatrading.com**. No selecciones acceso público ni anónimo.
5. Implementa y copia la URL terminada en **`/exec`**.
6. Abre ese enlace con tu cuenta BVT. Comparte solo ese enlace con el equipo; no compartas la base ni la carpeta de datos.

Si la opción del dominio no aparece, verifica que el propietario pertenezca al Workspace BVT y que las políticas de administración permitan aplicaciones internas. No publiques con un acceso más amplio para resolverlo.

Comprueba el enlace con otra cuenta BVT y con una cuenta externa. La externa debe quedar fuera. Si `Session.getActiveUser().getEmail()` resulta vacío por una política del dominio, la app deniega el acceso: nunca sustituye al usuario por el correo del propietario. El administrador debe revisar esa política. [Documentación de identidad de Google](https://developers.google.com/apps-script/reference/base/session).

## 7. Prueba los dos Excel de muestra

1. Crea un cliente real o de prueba para Amazon MX con país `MX` y moneda `MXN`.
2. Crea un proveedor real o de prueba para Nobby con país `DE` y moneda `EUR`.
3. En cada ficha usa **Importar lista de precios**. Los originales están en `muestras` y también en la carpeta original del proyecto.
4. Usa los valores detectados:

| Archivo | Hoja | Cabecera | Datos desde | Líneas | Precios |
| --- | --- | ---: | ---: | ---: | ---: |
| Amazon MX | ALL | 4 | 7 | 7.515 | 15.030 |
| Nobby | Tabelle1 | 7 | 8 | 7.515 | 45.061 |

5. Revisa el mapeo y confirma las monedas. Nobby propone fecha inicial `2025-08-15` desde sus metadatos. Las columnas de margen quedan fuera.
6. La validación debe mostrar una advertencia `invalid_ean` en cada archivo. El valor original `43917996264` se conserva; no se le agrega un cero. Ambos archivos tienen 1.970 ASIN vacíos.
7. Crea el borrador. Comprueba una línea y activa cuando corresponda. Volver a importar crea otra revisión; no modifica los precios anteriores.

Prueba opcional del recorrido de Google: sube ambos originales a Drive y crea las propiedades `MDM_TEST_AMAZON_ID` y `MDM_TEST_NOBBY_ID` con sus IDs. Ejecuta **`runSampleTests`** desde el editor. Usa conversiones temporales y no crea fichas ni listas. Los archivos temporales se envían a la papelera al terminar. Esta prueba consume tiempo de ejecución de Google.

## 8. Actualizaciones

Sustituye los archivos de código cambiados por sus versiones completas. Luego **Implementar → Gestionar implementaciones → Editar → Nueva versión → Implementar**. La URL `/exec` se mantiene. Recarga la página en los navegadores del equipo.

En esta primera entrega deben copiarse todos los archivos del paso 3 y el manifiesto. No reemplaces el Excel ni cambies `MDM_DATA_ID` al actualizar código. No vuelvas a cargar la base inicial sobre una base en uso.

## Copias y recuperación

La copia nocturna conserva las últimas **30 copias de `MDM_Data`**. También guarda una copia de las líneas de cada lista cuando su versión cambia, con nombre `Lines_ID_vVERSION`; estas copias se conservan para poder recuperar las referencias de las bases anteriores. Los Excel/CSV fuente se conservan en `Sources`. Las importaciones sin terminar caducan a las 24 horas y se limpian en la siguiente copia nocturna.

Para recuperar:

1. Evita que el equipo edite durante la recuperación. Haz una copia de la base actual.
2. En `Backups`, elige `MDM_Data_FECHA`. Cópiala y llámala `MDM_Data_restaurada`; no edites la copia de respaldo directamente.
3. En su hoja `PriceLists`, para cada fila busca en `Backups` el archivo `Lines_ID_vVERSION` que coincida con su `id` y `version`. Haz una copia de ese archivo en `PriceLists` y pon el ID de la copia en la columna `lines_file_id`. Esto recupera también las marcas, categorías y exclusiones que existían en esa fecha.
4. Cambia `MDM_DATA_ID` por el ID de la base restaurada y ejecuta `setup`.
5. Comprueba fichas y precios con la app antes de reabrir la edición al equipo.

Las copias son archivos reales y consumen espacio. La carpeta y el proyecto deben conservarse privados. El propietario de Google Drive puede modificar los archivos directamente: las protecciones de la app no son permisos SQL inmutables.

## Problemas habituales

| Síntoma | Solución |
| --- | --- |
| Falta configurar la base | Configura `MDM_DATA_ID` y ejecuta `setup`. |
| La estructura de una hoja no corresponde | Revisa que usaste el Excel entregado y no renombraste/reordenaste columnas. El código no sobrescribe la estructura. |
| `Drive is not defined` / servicio deshabilitado | Activa Drive API v3, identificador `Drive`. |
| No se puede abrir el archivo | Usa el ID del Google Sheets nativo y ejecuta con su propietario. |
| Acceso denegado con una cuenta BVT | Verifica dominio, despliegue interno y disponibilidad del correo del usuario; consulta la sección 6. |
| Sesión de página caducada | Recarga. El permiso de escritura de la página dura hasta seis horas y Google puede desalojar la caché antes. |
| Otra persona modificó el registro | Recarga la ficha y repite el cambio sobre su versión actual. |
| Importación interrumpida por conexión | En la ventana de validación pulsa Reintentar/continuar. No duplica bloques ya confirmados. Si cerraste o recargaste la página, vuelve a cargar el archivo; la operación anterior caducará. |
| Precios vacíos en un Excel con fórmulas | Abre, recalcula y guarda el archivo en Excel; la app usa los resultados guardados. Revisa el informe antes de importar. |
| Tiempo máximo/cuota de Google | Revisa Ejecuciones en Apps Script. Las validaciones van en bloques; la conversión inicial depende de Drive y del tamaño del libro. |
| Falló una copia nocturna | Revisa Activadores/Ejecuciones con la cuenta propietaria. Vuelve a ejecutar `nightlyBackup` y verifica espacio de Drive y permisos. |

Documentación oficial: [aplicaciones web](https://developers.google.com/apps-script/guides/web), [Drive avanzado](https://developers.google.com/apps-script/advanced/drive), [cuotas](https://developers.google.com/apps-script/guides/services/quotas).
