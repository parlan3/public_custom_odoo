# CDP

Autor y mantenimiento — Joaquin Romero, Nexar-it.

Versión 19.0.2.0.1 para Odoo 19 Enterprise. Corrige el orden de carga del menú histórico. Actualización del módulo técnico existente `nexar_it_contabilidad_pruebas`.

## Funciones

Facturas y notas de crédito de clientes y proveedores, cobros y pagos manuales, registro del pago desde la factura y conciliación de la cuenta por cobrar o pagar mediante los modelos y asistentes estándar de Odoo. Cada compañía tiene diarios y siete cuentas independientes CDP. Se crean dentro de las mismas compañías seleccionadas.

El titular ve los documentos fiscales con acceso de consulta. Crea y modifica operaciones CDP. Los demás usuarios normales tienen bloqueados los diarios, cuentas, comprobantes, pagos y apuntes CDP. El superusuario y el administrador de infraestructura pueden eludir las reglas de seguridad.

La protección incluye reglas globales, filtros obligatorios de propiedad incluso en búsquedas internas que omiten ACL, la vista SQL del análisis de facturas y los saldos y búsquedas de contactos. Un usuario convencional no obtiene acceso por seleccionar todos los diarios, enviar IDs CDP conocidos ni forzar el alcance combinado en las opciones de un reporte. El UID de superusuario queda exceptuado expresamente. Se incluyen pruebas de regresión específicas para estos recorridos, pendientes de ejecución en Odoo.sh.

El menú visible se llama CDP. Incluye mayor, balance y resultados en tres alcances, CDP, fiscal y combinado. Las entradas de reportes estándar abren por defecto el alcance fiscal. Los reportes CDP y combinados se abren desde sus menús respectivos. El selector estándar de diarios restringe adicionalmente cada reporte. Para seleccionar cuentas, guardar un filtro favorito privado por cuentas desde Apuntes y elegirlo en el filtro de apuntes del reporte.

Los importes CDP se contabilizan en los modelos normales de Odoo. Se excluyen de los reportes estándar mediante el alcance fiscal y de los usuarios normales mediante reglas globales. Una consulta SQL externa o una integración que utilice superusuario debe aplicar explícitamente su propio filtro CDP. Antes de aceptar un reporte personalizado ajeno al módulo, verificar que usa `_get_report_query` o `_get_options_domain` y respeta las reglas de registros.

## Alcance de esta entrega

Esta versión utiliza moneda de la compañía, líneas sin impuestos y pagos manuales. Genera comprobantes internos de simulación sin autorización fiscal. Los diarios tienen deshabilitados los documentos fiscales latinoamericanos. Se bloquean los enlaces públicos de portal y el envío mediante el asistente de facturas. La facturación fiscal electrónica, retenciones, impuestos simulados, multimoneda, distribuciones analíticas, facturación desde ventas/compras e integración de inventario requieren ampliaciones específicas. Las facturas se crean directamente desde CDP.

Los movimientos manuales de la versión inicial se conservan bajo Histórico manual. No se migran a facturas ni forman parte de los nuevos reportes combinados. Esa decisión evita duplicar o reinterpretar pruebas ya cargadas.

## Actualizar en staging

1. Respaldar la base de pruebas.
2. Reemplazar la carpeta `nexar_it_contabilidad_pruebas` del repositorio por la del ZIP. Conservar el mismo nombre técnico para actualizar la instalación existente.
3. Hacer commit y push en la rama staging y esperar el build.
4. En Aplicaciones, buscar CDP y pulsar Actualizar. El script de migración configura los diarios y cuentas estándar para los circuitos existentes y concede el grupo contable al titular. Las reglas globales mantienen bloqueada su edición fiscal.
5. Si se instala desde cero, ejecutar CDP / Configurar contabilidad de pruebas con un usuario administrador y seleccionar el usuario titular y sus compañías.
6. Cerrar y volver a abrir las sesiones para renovar menús y permisos.

## Pruebas antes de habilitar el uso

El código fue validado estáticamente. No fue instalado ni ejecutado contra el servidor de destino en esta entrega. Las pruebas TransactionCase incluidas deben ejecutarse en una copia de staging con `--test-enable --test-tags /nexar_it_contabilidad_pruebas --stop-after-init`, usando la configuración y base apropiadas del proyecto. Revisar el log completo y exigir cero fallos.

En cada compañía, crear una factura de cliente por 100, confirmarla y registrar el cobro desde Pagar usando CDP Caja. Debe quedar pagada y con residual cero. Repetir con una factura de proveedor por 40 y su pago. El mayor CDP debe mostrar caja por 60, clientes y proveedores saldados, ingreso 100 y gasto 40. Probar también pagos parciales, notas de crédito y pagos independientes seguidos de conciliación manual antes de habilitar esos recorridos.

Comprobar que el mayor fiscal excluye los apuntes CDP, el mayor CDP excluye los fiscales y el combinado muestra ambos. Probar selectores de diarios, filtros de cuentas, comparación por períodos y exportaciones PDF/XLSX. Comprobar el rechazo de modificación, cancelación y pago de comprobantes fiscales por el titular. Con otro usuario normal, probar búsquedas, enlaces directos, exportaciones y lectura por API de los IDs CDP conocidos. Revisar los reportes y asistentes específicos instalados en la base.

## Reversión y conservación de datos

Restaurar el respaldo si falla la actualización. Después de contabilizar operaciones CDP, conservar instalado el módulo para mantener su clasificación y seguridad. Desinstalarlo eliminaría las reglas que separan los datos, aunque los documentos contables estándar podrían permanecer. No desinstalarlo sobre una base con documentos CDP sin un procedimiento de migración y respaldo.
