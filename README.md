# ASISTENCIA DEL PARLAMENTO JOVEN 2026

App maestra multirregional para cargar una base general y actualizarla día a día sin borrar asistencias.

## Qué hace
- Importa Excel o CSV.
- Agrega nuevos participantes y actualiza existentes.
- Los campos vacíos de una carga nueva NO borran información ya guardada.
- Las asistencias existentes NO se borran al actualizar la base.
- Coincidencia para actualizar: ID_INTERNO → DNI → correo → celular → nombre+región.
- Sesiones independientes por región.
- Abrir/cerrar asistencia.
- Quitar asistencia de una sola persona.
- Reiniciar toda la asistencia de una sesión.
- Activar/desactivar participantes sin borrarlos.
- Exportar cada sesión a Excel.

## Columnas recomendadas
`ID_INTERNO, REGION, DNI, NOMBRES_APELLIDOS, CORREO, CELULAR, CAMARA, GRUPO_PARLAMENTARIO, OBSERVACION`

**Muy recomendable:** usa `ID_INTERNO` único y permanente para cada joven. Así podrás completar DNI/correo/celular después sin crear duplicados.

## Railway
Variables en el servicio web:
- `DATABASE_URL=${{Postgres.DATABASE_URL}}`
- `SECRET_KEY=una-clave-larga`
- `ADMIN_PASSWORD=tu-contraseña`

Esta versión no necesita variable REGION porque maneja todas las regiones.
