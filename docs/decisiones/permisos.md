# Permisos · Política y pruebas de las reglas

Fecha: 2026-10-29. Las reglas están en `.claude/settings.json`. En Windows, Claude Code corre comandos con dos herramientas, Bash y PowerShell, y cada una tiene reglas propias.

## Política y peor escenario
| Regla | Política | Lo peor que puede pasar sin ella |
|---|---|---|
| Leer .env | Prohibido | La llave entra al contexto y termina en un mensaje, un log o un commit; alguien la usa y agota la cuota |
| pip install | Preguntar | Entra código de terceros sin revisar, por ejemplo un paquete con un nombre parecido al real |
| git commit | Preguntar | Queda en el historial algo sin verificar, y el historial es lo que se evalúa |
| git push | Preguntar | Lo anterior queda publicado en GitHub y es difícil de borrar del todo |
| rm / Remove-Item | Preguntar | Se borra trabajo que no estaba en git |
| Editar producto/ | Sin preguntar | Un cambio malo en el código, que git permite deshacer |
| pytest | Sin preguntar | Corre las pruebas del propio proyecto; es como verifica su trabajo |

Entradas en `.claude/settings.json`:

| Regla | Lista | Entradas |
|---|---|---|
| Leer .env | `deny` | `Read(.env)`, `PowerShell(Get-Content *.env)` |
| pip install | `ask` | `Bash(pip install *)`, `Bash(python -m pip install *)`, `PowerShell(pip install *)`, `PowerShell(python -m pip install *)` |
| git commit | `ask` | `Bash(git commit *)`, `PowerShell(git commit *)` |
| git push | `ask` | `Bash(git push *)`, `PowerShell(git push *)` |
| rm / Remove-Item | `ask` | `Bash(rm *)`, `PowerShell(Remove-Item *)` |
| Editar producto/ | `allow` | `Edit(/producto/**)` |
| pytest | `allow` | `Bash(python -m pytest *)`, `PowerShell(python -m pytest *)` |

## Pruebas de la regla de PowerShell para .env
Se probó `PowerShell(Get-Content *.env)` con un archivo falso, `prueba-alias.env`, fuera del repo y con una sola línea de texto de prueba.

| Comando | Resultado |
|---|---|
| `Get-Content <ruta>` | Bloqueado. Es el control: confirma que la regla está cargada |
| `gc <ruta>`, `type <ruta>` y `cat <ruta>` | Bloqueados |
| `Get-Content "<ruta>"` y `Get-Content '<ruta>'` | Bloqueados |
| `if ($false) { Get-Content <ruta> }` | Bloqueado, aunque el bloque nunca se ejecuta |
| `Get-Content <ruta> -Raw` | **No bloqueado: el archivo se leyó** |

Los bloqueos respondieron `Permission to use PowerShell with command … has been denied.`

Con el `.env` del proyecto, cada comando fue dentro de `if ($false) { … }`, que nunca se ejecuta, así que el archivo no se leyó:

| Comando dentro de `if ($false) { … }` | Resultado |
|---|---|
| `Get-Content .env` | Bloqueado por la regla: `Permission to use PowerShell with command … has been denied.` |
| `Get-Content .env -Raw` | Bloqueado por la revisión de rutas: `get-content targeting '…\BioFocus\.env' was blocked.` |
| `Select-String -Path .env -Pattern x` | Bloqueado por la revisión de rutas: `select-string targeting '…\BioFocus\.env' was blocked.` |

El registro de la sesión marca los tres como rechazados por una regla de `.claude/settings.json` (`ruleSource: projectSettings`). `PowerShell(Get-Content *.env)` no coincide con los dos últimos, así que los bloqueó `Read(.env)`.

### Qué muestran
- **Alias:** la regla escrita para `Get-Content` cubre `gc`, `type` y `cat`, porque Claude Code traduce los alias comunes al nombre del cmdlet antes de comparar. `rm` y `del`, alias de `Remove-Item`, no se probaron para no tener que aprobar un borrado; según la documentación se traducen igual.
- **Comillas y bloques:** poner la ruta entre comillas o meter el comando en un `if` no esquiva la regla. Claude Code revisa cada comando, también los que están dentro de un bloque.
- **Hueco de `-Raw`:** con un parámetro después de la ruta, el comando ya no termina en `.env` y `PowerShell(Get-Content *.env)` deja de coincidir. En el `.env` del proyecto lo cubre `Read(.env)`, porque Claude Code revisa qué archivo leen `Get-Content` y `Select-String` y les aplica las reglas `Read`. El hueco solo afecta a archivos `.env` fuera del proyecto.
- **Regla opcional, sin aplicar:** `PowerShell(Get-Content *.env *)` en `deny` cerraría el hueco fuera del proyecto. Iría junto a la actual, no en su lugar: un ` *` final cubre también el comando sin parámetros solo cuando es el único comodín de la regla.
- **Límite de los scripts:** ninguna regla cubre un programa que abra el archivo por su cuenta, como un script de Python. Claude Code revisa el texto del comando, no lo que hace el programa. La documentación aclara que estas reglas no son una barrera de seguridad y recomienda el sandbox para bloquear el acceso a nivel del sistema operativo.

Fuente: [Configure permissions](https://code.claude.com/docs/en/permissions), documentación de Claude Code.
