# Nexar-it - Contabilidad de pruebas para Odoo 19

Autor y mantenimiento — Joaquin Romero, Nexar-it.

Versión 19.0.1.1.0. Módulo propio para instalar y validar en staging.

## Alcance

Libro independiente de simulación en las compañías seleccionadas durante la configuración. Un único usuario titular seleccionado por el administrador. El menú contiene movimientos, mayor, balance y cuentas. Se generan cinco diarios por compañía y una copia inicial de su plan de cuentas activo. Los importes se expresan en la moneda de cada compañía.

Los movimientos se cargan manualmente con líneas de debe y haber. Para una venta se debita la cuenta por cobrar y se acredita el ingreso. Para un cobro se debita caja o banco y se acredita la cuenta por cobrar. Las compras y los pagos se registran del mismo modo con sus cuentas correspondientes. El campo tercero es texto de prueba. Las cuentas se seleccionan del plan copiado.

Esta versión no incluye facturas con productos y cálculo automático de impuestos, vencimientos, conciliación automática, retenciones, multimoneda transaccional, stock ni conexión bancaria. Si se necesita reproducir esos asistentes estándar, hace falta ampliar y probar el módulo antes de considerarlo equivalente al circuito completo de Odoo.

Los datos viven en modelos `nexar.test.*`. No generan asientos en `account.move`, documentos ARCA ni movimientos de stock. Los informes fiscales y estados contables estándar no incorporan este libro. Los reportes propios muestran exclusivamente movimientos confirmados. Las modificaciones requieren volver a borrador y conservan el número. No se permite eliminar movimientos completos. Esta versión conserva fecha de última modificación, sin historial de versiones.

## Seguridad

ACL específicas y reglas globales exigen titular coincidente y compañía permitida, incluso si a otro usuario se le asigna accidentalmente el grupo del módulo. Los usuarios normales no tienen menú ni acceso por API a estos modelos. El usuario titular conserva Accounting / Read-only. Reglas globales adicionales impiden escrituras en los principales modelos contables fiscales aun si se agrega accidentalmente el grupo de contabilidad.

No hay portal, enlaces públicos, adjuntos ni chatter propios del circuito. El superusuario y quien administra la base o el código pueden eludir o cambiar la seguridad. No es una barrera frente al administrador de infraestructura.

## Instalación directa en el repositorio

1. Guardar un respaldo de la base staging.
2. Descomprimir el ZIP y copiar la carpeta `nexar_it_contabilidad_pruebas` completa en la raíz del repositorio de la rama staging de Odoo.sh, o en una carpeta de addons ya detectada por el proyecto.
3. Hacer commit y push. Esperar a que el build termine correctamente.
4. Abrir la base staging, activar modo desarrollador y entrar en Aplicaciones. Actualizar la lista de aplicaciones.
5. Buscar `Nexar-it - Contabilidad de pruebas` e instalarlo.
6. Abrir Nexar-it / Configurar contabilidad de pruebas. Seleccionar las compañías y un usuario interno dedicado a pruebas. Confirmar el reemplazo de sus grupos y compañías y pulsar Configurar circuitos.
7. Comprobar con superusuario un circuito y cinco diarios por compañía seleccionada, con cuentas en cada circuito.
8. Establecer la contraseña del usuario seleccionado en Ajustes / Usuarios y probar en una sesión independiente.

También puede alojarse la carpeta en un repositorio propio y agregarse ese repositorio como submódulo. El ZIP se descomprime antes de subirlo al repositorio.

La configuración se ejecuta desde el asistente y exige staging o una base neutralizada. Fija las compañías seleccionadas y reemplaza los grupos del usuario por usuario interno, multicompañía, consulta contable y operador de pruebas. La compañía inicial es la seleccionada con menor ID. Repetir la misma configuración es seguro. Una selección diferente requiere revisión para evitar dejar circuitos sin acceso. El paquete contiene únicamente nombres genéricos y la autoría de Joaquin Romero, Nexar-it.

## Verificación obligatoria en Odoo.sh

Se incluyen pruebas TransactionCase etiquetadas `post_install`. Ejecutarlas sobre una copia desechable del staging con el runner de Odoo y `--test-enable --test-tags /nexar_it_contabilidad_pruebas --stop-after-init`, instalando o actualizando el módulo según corresponda. Revisar el log completo y exigir cero fallos. La sintaxis exacta del comando debe usar la configuración y la base de la copia de pruebas del proyecto.

Además de las pruebas automatizadas, verificar en la interfaz con sesiones independientes:

- Usuario titular ve solamente las compañías seleccionadas y puede consultar facturas, asientos y reportes fiscales. Intentar crear, editar, contabilizar, cancelar y conciliar registros fiscales debe fallar.
- Crear una venta simulada y su cobro mediante dos asientos balanceados en cada compañía. Confirmar, volver a borrador, editar y confirmar. Verificar mayor y balance.
- Anotar totales y cantidades fiscales antes y después. Deben permanecer iguales, también al abrir reportes como administrador.
- Usuario normal de cada compañía no ve el menú y no puede leer por enlace directo ni por API IDs conocidos de circuitos, cuentas, diarios, movimientos o apuntes. Comprobar búsquedas, exportaciones y agrupaciones.
- Intentar usar una cuenta de otra compañía, alterar directamente el estado por API y modificar líneas confirmadas. Debe fallar.
- Verificar que el usuario no ve compañías ajenas a la selección, y que las reglas no impiden el trabajo contable normal de los demás usuarios.

## Estado de validación

El paquete fue revisado estáticamente con análisis de sintaxis Python, XML, CSV y referencias internas. No se ejecutó contra un servidor Odoo 19 ni se instaló en un servidor de destino. Las pruebas de integración y seguridad deben aprobarse en Odoo.sh antes de habilitar su uso. Esta entrega cubre un libro manual de simulación y requiere validación funcional del alcance.

## Reversión

Antes de cargar datos, puede desinstalarse para retirar modelos, menús y reglas. La desinstalación elimina los datos de los modelos de pruebas. Después de cargar datos, exportar y respaldar primero. Los grupos y compañías del usuario se ajustaron mediante el asistente y deben restaurarse manualmente si se revierte. Los datos fiscales no son modificados por el libro de pruebas.
