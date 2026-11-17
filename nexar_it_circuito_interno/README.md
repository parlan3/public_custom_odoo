# Nexar Circuito Interno para Odoo 19

Versión 19.0.1.0.3 · Nexar IT · LGPL-3

## Estado de entrega

Paquete preparado para instalar y validar en staging. Se verificaron sintaxis Python, XML, archivos declarados y referencias XML externas existentes en la base del cliente. Se revisaron los métodos de cuentas, pagos y diferencias de cambio contra el código oficial de Odoo 19.

Las pruebas de integración incluidas todavía deben ejecutarse en un servidor Odoo 19 Enterprise. La versión 19.0.1.0.1 quedó instalada y configurada en el entorno de pruebas; la confirmación de una venta detectó un bloqueo del control analítico adicional. Esta versión 19.0.1.0.3 incluye la corrección de compatibilidad, la activación explícita del menú por usuario y la revisión de textos. Estas últimas correcciones requieren despliegue y actualización antes de verificarlas en Odoo. Esta entrega no certifica que el circuito esté listo para uso del cliente.

## Alcance

Circuito independiente sobre los modelos contables nativos, con un titular y varias compañías cuya moneda principal sea ARS. Incluye ventas, compras, notas de crédito, cobros y pagos manuales en ARS y USD y selección de contrapartidas internas. Las diferencias de cambio de conciliación utilizan el diario INTFX y cuentas propias.

Las cuentas del cliente/proveedor y del producto se sustituyen en los documentos internos por las cuentas del circuito. Las propiedades compartidas del contacto se conservan. Las líneas internas se mantienen sin impuestos ni distribución analítica. Los comprobantes internos tienen los documentos latinoamericanos desactivados y punto de venta ARCA cero.

El alcance se centra en documentos contables y pagos manuales. Inventario, valoración de stock, ventas desde POS, emisión electrónica, retenciones, conexión bancaria, importaciones de extractos y modelos de conciliación automática quedan fuera de esta versión. Para el circuito use conceptos de servicio o líneas manuales.

## Contenido por compañía

| Código | Diario | Tipo |
| --- | --- | --- |
| INTV | Interno Ventas | Ventas |
| INTC | Interno Compras | Compras |
| INARS | Interno Caja ARS | Efectivo ARS |
| INUSD | Interno Caja USD | Efectivo USD |
| INTAJ | Interno Ajustes | General |
| INTFX | Interno Diferencias de cambio | General |

Se conservan las nueve cuentas internas ya creadas y se agregan dos cuentas de diferencia de cambio. El resultado previsto para las cuatro empresas es 24 diarios y 44 cuentas internas. La configuración vincula los registros existentes que coinciden exactamente en código, nombre, compañía y tipo. Rechaza coincidencias ambiguas o registros con apuntes previos que aún no estén clasificados.

## Dependencias y ubicación

- Odoo 19 Enterprise.
- Módulos account, account_reports y l10n_ar.
- No depende de nexar_it_contabilidad_pruebas. Puede coexistir con él usando otro usuario titular.
- Carpeta del addon nexar_it_circuito_interno dentro del repositorio de addons detectado por Odoo.sh.

Si public_custom_odoo sigue siendo el repositorio custom de parlan3, colocar allí esta carpeta. El nombre de repositorio y la rama activa deben confirmarse en el proyecto Odoo.sh. Este ZIP contiene el addon, no un repositorio remoto ya publicado.

## Instalación en la base de pruebas

1. Tomar un respaldo de la base de staging y registrar los grupos y compañías actuales del usuario titular.
2. Descomprimir el ZIP. Copiar la carpeta nexar_it_circuito_interno completa al directorio de addons del repositorio. Evitar un nivel de carpetas adicional.
3. Hacer commit y push a la rama de staging. Esperar que el build termine correctamente.
4. Abrir staging con un administrador. Actualizar la lista de aplicaciones en modo desarrollador.
5. Buscar Nexar Circuito Interno e instalar. La instalación agrega modelos, reglas y asistente. La clasificación de los diarios se realiza en el paso siguiente.
6. En Ajustes > Usuarios y compañías > Usuarios, abrir el administrador que realizará la configuración. En Derechos de acceso, marcar Mostrar Circuito interno y guardar. Habilitar también la casilla para el titular que operará el circuito. Luego abrir Circuito interno > Configurar circuito.
7. Seleccionar las cuatro compañías U J S.A., Universo Producciones S.A., Entre Actos Gourmet S.A. y Elysium Arena S.A.
8. Seleccionar el usuario ya creado usuario-contabilidad-prueba. El paquete no incluye contraseñas ni modifica la contraseña existente.
9. Marcar la confirmación de asignación exclusiva y dejar activado Reemplazar las reglas manuales de esta implementación.
10. Pulsar Configurar circuito. El asistente configura todo en una transacción. Ante un error, corregir su causa antes de repetir.
11. Cerrar la sesión del titular e ingresar nuevamente. Abrir Contabilidad, seleccionar la compañía y comprobar los diarios internos.
12. Ejecutar las pruebas indicadas antes de habilitar al cliente.

El asistente reemplaza los grupos del titular por usuario interno, multicompañía y operador de circuito interno, que incluye el permiso contable operativo. Su configuración no admite un administrador ni un titular de CDP. Repetir la misma selección es idempotente. Cambiar titular o compañías posteriormente requiere una migración revisada.

Las once reglas manuales anteriores se desactivan únicamente si su nombre, modelo y dominio coinciden exactamente con los generados para estos diarios, cuentas y titular. Se mantienen para trazabilidad y son sustituidas por reglas del módulo. Si fueron alteradas, el asistente detiene la configuración y revierte la transacción.

## Operación del titular

### Venta y cobro

1. En Contabilidad crear una factura de cliente en Interno Ventas.
2. Seleccionar compañía, cliente, fecha y moneda ARS o USD.
3. Agregar una línea manual con concepto, cantidad e importe.
4. Revisar que la línea use Ingresos por ventas internas y la contrapartida Clientes internos, sin impuestos.
5. Confirmar el documento.
6. Registrar el pago utilizando Interno Caja ARS o Interno Caja USD según la moneda del pago y método manual.
7. Revisar el saldo residual, el estado pagado y los apuntes generados.

### Compra y pago

Repetir el circuito desde facturas de proveedor con Interno Compras. La línea utiliza Gastos por compras internas y la contrapartida Proveedores internos. Registrar el pago desde la caja de la moneda correspondiente.

### USD y diferencias de cambio

La compañía conserva ARS como moneda contable. Los documentos y la caja USD registran importe en dólares y su equivalente contable. Las cotizaciones deben estar cargadas por fecha para cada compañía. Cuando una conciliación genera diferencia de cambio, el módulo la dirige a Interno Diferencias de cambio, Ganancia de cambio interna y Perdida de cambio interna.

Las transferencias y ajustes manuales se registran con INTAJ y las cuentas propias del circuito, con líneas balanceadas y monedas consistentes. No hay un nuevo asistente de transferencia automática.

## Visibilidad e informes

El titular accede a sus registros internos de las compañías habilitadas. Los usuarios habituales quedan excluidos de esos diarios, cuentas, movimientos, apuntes, pagos, conciliaciones, mensajes y adjuntos vinculados.

Los informes del motor account.report reciben un dominio obligatorio según el usuario. El análisis de facturas y los saldos de clientes/proveedores incluyen el filtro correspondiente. Las búsquedas ORM elevadas con sudo conservan el filtro de identidad, salvo el superusuario real. Los envíos de comprobantes, suscripciones y acceso público por token están bloqueados para documentos internos.

El superusuario, el administrador de infraestructura y las consultas SQL externas pueden acceder a los datos. Los reportes personalizados de terceros que usen SQL independiente deben auditarse por separado. El circuito usa registros del libro nativo, por lo que la visibilidad aplicada por este módulo debe comprobarse en cada salida que utilice el cliente.

## Pruebas automatizadas incluidas

En una copia desechable de staging con el código y las dependencias presentes, ejecutar el runner de Odoo sobre la base de esa copia.

Ejemplo para instalación inicial, sustituyendo los marcadores por los valores del proyecto:

    odoo-bin -c <configuracion> -d <base_copia_pruebas> -i nexar_it_circuito_interno --test-enable --test-tags /nexar_it_circuito_interno --stop-after-init

Si ya está instalado, utilizar -u nexar_it_circuito_interno en lugar de -i.

Las pruebas crean cuatro compañías de prueba y usuarios temporales dentro de las transacciones del runner. Cubren ventas y compras ARS/USD, pagos, diferencias de cambio, privacidad de lecturas y exportaciones, acceso elevado, informes, adjuntos, notas de crédito y configuración repetida.

Exigir cero fallos y revisar los logs completos. Un build exitoso sin ejecución de los tests no equivale a su aprobación.

## Prueba de aceptación en la base del cliente

- Entrar como titular y verificar 6 diarios y 11 cuentas por compañía.
- Crear venta ARS, compra ARS, venta USD y compra USD en cada compañía, por importes reconocibles de prueba.
- Registrar los cobros y pagos, comprobar residual cero y cuentas correctas.
- Usar dos fechas con cotizaciones distintas para verificar INTFX, sin modificar cotizaciones de producción.
- Crear una nota de crédito y comprobar sus cuentas y conciliación.
- Intentar usar cuentas o diarios de otra compañía y del circuito habitual. Debe rechazarse.
- Abrir los mismos registros por enlace directo y mediante exportación como otro usuario. Debe rechazarse.
- Comparar Mayor, Balance, Resultados, saldos de terceros y exportaciones antes y después como usuario habitual. Los movimientos internos deben permanecer excluidos.
- Revisar los informes del titular para confirmar que los apuntes internos estén incluidos.
- Confirmar que los usuarios habituales puedan seguir operando su contabilidad.
- Registrar versión, fecha, usuarios, compañías, resultados y evidencias.

## Reversión

La desinstalación elimina los campos y las reglas del módulo y puede exponer registros que antes estaban restringidos. Después de cargar datos, la vía de reversión recomendada es restaurar el respaldo de la base de pruebas. Antes de cualquier otra migración, conservar la clasificación de diarios y cuentas, las reglas y los permisos del usuario. La contraseña se administra por los mecanismos normales de Odoo.

## Referencias de implementación

Código oficial Odoo 19 revisado en https://github.com/odoo/odoo/tree/19.0/addons/account, especialmente account_move_line, account_payment y account_full_reconcile. Localización de Argentina en https://github.com/odoo/odoo/tree/19.0/addons/l10n_ar.

Fecha de preparación 17 de noviembre de 2026.


## Actualización desde 19.0.1.0.0

Reemplazar la carpeta del addon por esta revisión, publicar el cambio en la rama 19.0 del repositorio custom y actualizar su referencia en stage-1. Confirmar el build. En Aplicaciones, actualizar Nexar Circuito Interno si Odoo.sh no ejecutó la actualización automática. Verificar la versión 19.0.1.0.1 y repetir Configurar circuito con las cuatro empresas y el titular.

El fallo detectado en staging ocurrió antes de confirmar la transacción de configuración. Las reglas manuales y el permiso de consulta del titular deben seguir vigentes hasta que el asistente finalice.


## Revisión 19.0.1.0.2

La revisión 19.0.1.0.1 se instaló y actualizó correctamente. El asistente configuró las cuatro compañías, 24 diarios y 44 cuentas, y retiró las once reglas manuales. La creación de una venta utilizó correctamente las cuentas internas. Su confirmación detectó un conflicto con vippinn_ea_analytic_control, ya instalado en esta base.

Esta revisión declara ese módulo como dependencia para garantizar el orden de carga y aplica su control analítico exclusivamente a los movimientos habituales. Los movimientos internos mantienen su restricción de analítica vacía. El control estándar de planes analíticos recibe la misma delimitación por circuito.

Reemplazar la carpeta completa, desplegar en stage-1 y actualizar Nexar Circuito Interno. No hace falta reinstalar ni recrear los circuitos. Después de actualizar se debe restituir el permiso operativo desde el asistente para el mismo titular y compañías, y repetir las pruebas.

Dependencia específica de este proyecto: vippinn_ea_analytic_control. En otras instalaciones este paquete requiere también ese addon custom. La compatibilidad y las pruebas de la revisión 19.0.1.0.2 están pendientes de ejecutarse en staging.


## Revisión 19.0.1.0.3

El menú Circuito interno queda oculto por defecto para todos los usuarios, incluidos los administradores habituales. El módulo agrega la casilla Mostrar Circuito interno en Ajustes > Usuarios y compañías > Usuarios > Derechos de acceso. Solo un administrador de Ajustes puede activarla.

La casilla habilita la visibilidad del menú. Los permisos contables existentes y las reglas del titular siguen determinando el acceso a los datos. Desmarcar la casilla oculta el menú, pero no revoca por sí solo accesos que el usuario ya tenga desde Contabilidad o la API.

El titular habilitado dispone de accesos a Ventas internas, Compras internas, Cobros y pagos internos y Asientos internos. El administrador habilitado puede abrir Configurar circuito. El asistente conserva la elección de visibilidad al reasignar los grupos operativos del titular.

La ficha técnica del addon sigue administrándose desde Aplicaciones por los administradores autorizados. El superusuario real de Odoo puede omitir controles de acceso. La visibilidad por menú no constituye una barrera frente a la administración técnica de la base.

Se normalizó la codificación de los textos propios del módulo y se revisaron etiquetas, mensajes de validación, avisos, títulos, botones y documentación. Los literales Python usan escapes Unicode para preservar los acentos incluso si una herramienta vuelve a guardar el archivo con otra codificación. XML y documentación se guardan en UTF-8. Los textos heredados de Odoo y otros módulos dependen de sus traducciones instaladas.

Actualizar a esta revisión y habilitar expresamente el menú en los usuarios necesarios. La revisión incluye también la compatibilidad analítica de 19.0.1.0.2. Las pruebas operativas continúan pendientes del despliegue.
