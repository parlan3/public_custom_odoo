# Nexar Visibilidad Contable — Odoo 19

Versión 19.0.1.0.2. Complemento de seguridad sobre Contabilidad nativa.
Depende de `account` y `account_reports` (Enterprise). No depende de CDP ni de
`nexar_it_circuito_interno`. No crea diarios, cuentas, asientos ni informes.

## Estado de entrega

La versión 19.0.1.0.1 está instalada en test desde el 19/11/2026. Se verificaron
lecturas directas y exportación de registros bloqueadas para el administrador
sin acceso; consulta sin escritura para Gerencia; 16 operaciones ARS/USD;
Balance, Resultados y Libro mayor; y equivalencia entre ambos circuitos y
la suma de sus reportes separados en las cuatro empresas.

Esta versión 19.0.1.0.2 corrige únicamente la representación del perfil Solo
consulta en el selector del usuario: Odoo 19 distingue grupos directos e
implícitos. Su despliegue y verificación en test están pendientes. La seguridad
efectiva de Gerencia en 1.0.1 fue comprobada; se explicitó su grupo de consulta
para mostrar correctamente el selector en esa versión. No es aprobación para
producción ni certificación de integraciones o informes externos.

## Configuración

1. Instalar el módulo desde Aplicaciones, quitando el filtro Aplicaciones si
   no aparece. No instalar el anterior `nexar_it_circuito_interno`.
2. En Ajustes → Usuarios, seleccionar el nivel en «Circuito contable
   restringido». Todos comienzan sin acceso, incluido el administrador común.
3. Habilitar temporalmente Operación al administrador que vaya a clasificar.
4. En cada diario y cuenta del circuito, marcar «Circuito con acceso
   restringido». Marcar tanto los diarios como las cuentas auxiliares.
   Si existen enlaces públicos, primero revocarlos: el módulo rechaza la
   clasificación de documentos o adjuntos que mantengan esos enlaces.
5. Asignar Operación al usuario operativo. Preparar Gerencia con permisos
   nativos de solo lectura y el nivel Solo consulta. Revisar las empresas
   autorizadas. Quitar el acceso temporal del administrador al finalizar.
6. Probar los tres perfiles antes de activar Gerencia o entregar al cliente.

| Nivel | Ver circuito restringido | Modificar circuito restringido |
|---|---|---|
| Sin acceso | No | No |
| Solo consulta | Sí | No |
| Operación | Sí | Según permisos contables nativos |

Los permisos se aplican además de los permisos y reglas de empresas nativos.
Elegir Solo consulta no quita permisos de escritura previamente otorgados sobre
el circuito ordinario. Para una Gerencia completamente de consulta, usar un
usuario dedicado sin grupos contables de escritura. Al bajar de Operación a
Consulta, revisar los grupos contables nativos que hayan quedado asignados.

## Alcance

Reglas globales de registros para diarios, cuentas, asientos, apuntes, pagos,
métodos de pago, extractos, conciliaciones y líneas analíticas. Protege también
mensajes, actividades, seguidores y adjuntos vinculados a esos modelos.
La clasificación del asiento depende de su diario y de las cuentas de sus
líneas; las líneas heredan la clasificación del asiento completo.

No es solo ocultación de menús: las lecturas directas por identificador y
las exportaciones usan las mismas reglas de servidor. Se comprueba además la
clasificación después de una modificación para impedir convertir un registro
ordinario en restringido sin permiso de operación.

Los informes contables nativos conservan sus cálculos y filtros. El complemento
limita las fuentes de datos de los informes contables, análisis de facturas y
saldos de contactos. Los usuarios habilitados pueden incluir ambos circuitos o
filtrar los diarios de uno. Esto no incorpora eliminación de operaciones entre
empresas ni un motor nuevo de consolidación multimoneda.

Los documentos restringidos no admiten enlaces públicos ni envío mediante el
asistente nativo de facturas. Las notas permanecen en el documento; se suprimen
sus notificaciones externas, por correo, bandeja y push, para no distribuir
copias a seguidores que hayan perdido acceso. Las copias enviadas antes de
instalar el módulo no pueden retirarse automáticamente.

## Límites técnicos que deben comprobarse

El superusuario técnico y código servidor que utilice `sudo()` o SQL directo
pueden omitir las reglas nativas de Odoo. Un administrador normal sin el grupo
no recibe acceso al circuito, pero quien administra los permisos puede
otorgárselo expresamente. No se pretende aislar datos del operador de la base
de datos ni de quien puede modificar el servidor.

Antes de producción, revisar integraciones, informes personalizados, acciones
automatizadas, informes enviados por correo y módulos que consulten con SQL o
privilegios elevados. No afirmar cobertura universal de desarrollos externos.
Las cuentas y diarios deben clasificarse antes de comenzar a operar. Las
operaciones entre circuitos pueden hacer que el asiento completo sea restringido.

## Pruebas incluidas

En una base desechable de Odoo 19 Enterprise con localización configurada:

```bash
odoo-bin -d BASE_DE_PRUEBAS -i nexar_it_visibilidad_contable --test-enable --test-tags /nexar_it_visibilidad_contable --stop-after-init
```

Usar `-u` en lugar de `-i` si ya estaba instalado. No ejecutar esa orden contra
producción. Las pruebas cubren acceso directo/exportación, administrador sin
grupo, consulta con permisos contables amplios, operación, cambio de
clasificación, adjuntos después de cargar la caché, enlaces públicos,
notificaciones, concesión/revocación, informes y separación de empresas.

En el stage real repetir ventas, compras, cobros y pagos ARS/USD con Operación;
comparar Balance, Resultados y Libro mayor con ambos circuitos y por diarios;
abrir las mismas URLs con Gerencia y con un usuario no habilitado. Probar
exportaciones PDF/XLSX y acciones de contabilizar, cancelar, revertir y conciliar.

## Despliegue

Copiar la carpeta completa `nexar_it_visibilidad_contable` a
`parlan3/public_custom_odoo`, rama `19.0`; confirmar y subir. Actualizar la
referencia de ese submódulo en la rama del proyecto Odoo.sh vinculada al stage
y esperar el build. Luego actualizar la lista de aplicaciones e instalar.
La instalación por sí sola no marca los diarios y cuentas existentes.
