# Hyperflix: informe de ejecución

## Modelo implementado

Hyperflix usa MongoDB Atlas con un modelo OLTP y una colección analítica OLAP:

- `usuarios`: perfiles, plan, ciudad y fecha de registro.
- `peliculas`: catálogo, género, duración, director y fecha de estreno.
- `reproducciones`: eventos de visualización con usuario, película, dispositivo, calidad, estado y progreso.
- `reproducciones_analiticas`: hechos enriquecidos con dimensiones de usuario y película para consultas agregadas.

La configuración se centraliza en `config.py`. Las credenciales se cargan desde `.env` y no se escriben en el código.

## Ejecución desde cero

1. `python Mongo/scripts/limpiar_bd.py`
2. `python Mongo/conexion.py`
3. `python Mongo/scripts/crear_estructura.py`
4. `python Mongo/scripts/generar_datos_masivos.py`
5. `python Mongo/scripts/transformar_oltp_a_olap.py`
6. `python Mongo/scripts/benchmarking_consultas.py`

El primer paso exige escribir `HYPERFLIX` y elimina únicamente la base configurada en `DB_NAME`.

## Resultado ejecutado

- Base: `HYPERFLIX-BD`
- Usuarios: 5.001
- Películas: 1.001
- Reproducciones: 50.001
- Registros analíticos: 50.001
- Generación masiva: 221,77 s
- ETL OLTP a OLAP: 27,67 s

Los registros analíticos conservan el `_id` de la reproducción y se escriben con `$merge` usando `whenMatched: replace`; la transformación puede repetirse sin duplicar hechos.

## Benchmark ejecutado

| Consulta | Filas | Latencia |
| --- | ---: | ---: |
| Reproducciones y minutos totales mensuales | 13 | 204,29 ms |
| Top 5 películas por género | 7 | 266,51 ms |
| Rendimiento por segmento y ciudad | 1.995 | 4.601,22 ms |
| Valor promedio por dispositivo | 5 | 250,78 ms |
| Reproducciones por día de la semana | 7 | 254,68 ms |
| **Promedio** | - | **1.115,50 ms** |

La tercera consulta es la más costosa porque agrupa y ordena 1.995 combinaciones de segmento y ciudad en un cluster Atlas de recursos limitados. Los índices creados cubren fecha, género/valor, segmento/ciudad y estado/segmento/ciudad.
