import datetime
import re
from collections import defaultdict

from gorrabot.config import config

BACKLOG_MILESTONE = config()['gitlab'].get('BACKLOG_MILESTONE', [])

OLD_MEMBERS = config()['gitlab'].get('OLD_MEMBERS', [])

MSG_MISSING_CHANGELOG = (
    'Si que te aprueben un merge request tu quieres, tocar el changelog tu '
    'debes'
)
MSG_CHANGELOG_DOSENT_PREFIX = "Los CHANGELOGS deberian empezar con [ADD], [MOD], [FIX], [DEL]" \
                                          "acorde al cambio y parece que tu changelog no lo esta haciendo, por favor" \
                                          "agregalo cuanod puedas"
NO_VALID_CHANGELOG_FILETYPE = (
    'El fichero que se creó en el directorio `CHANGELOG` no tiene extensión '
    '`{changelog_filetype}` por lo que no va a ser tomado en cuenta por el sistema de '
    'generación de changelogs. Hay que arreglar esto para que se pueda '
    'mergear el MR.'
)
MSG_TKT_MR = (
    'Tener merge requests con `Tkt ` en el título no es muy útil ya que '
    'puedo ver esa información en el nombre del branch. Se podría usar un '
    'título más descriptivo para este merge request.'
)
MSG_BAD_BRANCH_NAME = (
    'Los nombres de branch deben tener el formato tkt_XXX_1234_short_desc. '
    'Es decir, tienen que tener la versión para la que se quieren mergear '
    '{main_branches}, el número de ticket y una descripción corta.'
    '\n\n'
    'En caso de que sea un ticket de soporte usar el prefijo sup en vez de '
    'tkt. Si se trata de un branch experimental que no va a ser mergeado a '
    'corto plazo se puede usar el prefijo exp en vez de tkt.'
    '\n\n'
    'Esta te la dejo pasar, la próxima recordá usar esta nomenclatura!'
)
MSG_NEW_MR_CREATED = (
    'Vi que pusheaste a este branch pero no había ningún merge request '
    'creado. Me tomé la molestia de crearlo por vos, usando la información '
    'de un merge request de {base_branch}. Si tenés que hacer más cambios (es decir, '
    'no se trata de un simple merge), poné el MR en WIP/Draft para aclarar que'
    ' todavía no está terminado.'
)
MSG_CHECK_SUPERIOR_MR = (
    'Noté que mergeaste el branch que implementa esto para una versión '
    'anterior {prev_main_branches}. Hay que mergear este MR también para evitar que '
    'haya conflictos entre {main_branches}.'
)
MSG_STALE_MR = """
Noté que este merge request está en WIP/Draft y sin actividad hace bastante 
tiempo.
Para evitar que quede obsoleto e inmergeable, estaría bueno mirarlo. Te
recomiendo proceder con alguna de estas acciones:

* Si ya está listo para mergear, sacale el `WIP: ` o `Draft: ` del título y 
  esperá a que reciba feedback
* Si se trata de un merge request experimental o pensado a largo plazo, cambiá
  el nombre del source branch de `tkt_....` a `exp_....` para que lo tenga en
  cuenta
* Si te parece que los cambios no son más requeridos, cerrá el merge request
* En caso contrario, hacé las modificaciones que sean necesarias y sacarle
  el WIP o Draft
* También se puede agregar el label especial `no-me-apures` para que no vuelva
  a mostrar este mensaje en este merge request. Esto es una inhibición de mis
  gorra-poderes así que prefiero que no se abuse de esta opción
"""
MSG_MR_OLD_MEMBER = (
    'Este merge request no está listo y está asignado a un usuario '
    'que ya no forma parte del equipo. Habría que cerrarlo o reasignárselo a '
    'alguien más'
)
MSG_WITHOUT_PRIORITY = "No tiene `priority`"
MSG_WITHOUT_SEVERITY = "No tiene `severity`"
MSG_WITHOUT_WEIGHT = "No tiene peso!"
MSG_WITHOUT_MILESTONE = "No tiene milestone!"
MSG_WITHOUT_ITERATION = "No tiene iteration!"
MSG_NOTIFICATION_PREFIX_WITH_USER = "@{user} commiteo a la rama {branch} ({project_name}), pero esa rama:"
MSG_NOTIFICATION_PREFIX_WITHOUT_USER = "{user} (No lo encontre en mi DB) commiteo a la rama {branch} ({project_name})" \
                                       ", pero esa rama:"
MSG_BACKLOG_MILESTONE = "Tiene Backlog como milestone!"
CHANGELOG_PREFIX = re.compile("^(\[ADD|FIX|MOD|DEL\])")

# Define inactivity as a merge request whose last commit is older than
# now() - inactivity_time
inactivity_time = datetime.timedelta(days=config()['gitlab'].get('inactivity_time', 30))

# Time to wait until a new message indicating the MR is stale is created
stale_mr_message_interval = datetime.timedelta(days=config()['gitlab'].get('stale_mr_message_interval', 7))

# Time to wait until a new message indicating the MR is stale is created
decision_issue_message_interval = datetime.timedelta(days=config()['gitlab'].get('decision_issue_message_interval', 0))


__other_regex = {
    project_name: config()['projects'][project_name]['regex']
    for project_name in config()['projects']
    if 'regex' in config()['projects'][project_name]
}
# iid must be with this format: "P<iid>\d+"
regex_dict = defaultdict(lambda: r'^(?:tkt|mig|sup|exp)_(?P<iid>\d+|y2k)[-_].+', __other_regex)

