import datetime
from collections import defaultdict

OLD_MEMBERS = [
    '***REMOVED***', '***REMOVED***', '***REMOVED***', '***REMOVED***', '***REMOVED***',
    '***REMOVED***', '***REMOVED***', '***REMOVED***']

MSG_MISSING_CHANGELOG = (
    'Si que te aprueben un merge request tu quieres, tocar el changelog tu '
    'debes'
)
NO_MD_CHANGELOG = (
    'El fichero que se creó en el directorio `CHANGELOG` no tiene extensión '
    '`.md` por lo que no va a ser tomado en cuenta por el sistema de '
    'generación de changelogs. Hay que arreglar esto para que se pueda '
    'mergear el MR.'
)
MSG_TKT_MR = (
    'Tener merge requests con `Tkt ` en el título no es muy útil ya que '
    'puedo ver esa información en el nombre del branch. Se podría usar un '
    'título más descriptivo para este merge request.'
)
MSG_BAD_BRANCH_NAME = (
    'Los nombres de branch deben tener el formato tkt_***REMOVED***_1234_short_desc. '
    'Es decir, tienen que tener la versión para la que se quieren mergear '
    '(***REMOVED***, ***REMOVED*** o ***REMOVED***), el número de ticket y una descripción corta.'
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
    'de un merge request de ***REMOVED***. Si tenés que hacer más cambios (es decir, '
    'no se trata de un simple merge), poné el MR en WIP para aclarar que '
    'todavía no está terminado.'
)
MSG_CHECK_SUPERIOR_MR = (
    'Noté que mergeaste el branch que implementa esto para una versión '
    'anterior (***REMOVED*** o ***REMOVED***). Hay que mergear este MR también para evitar que '
    'haya conflictos entre ***REMOVED***/dev, ***REMOVED***/dev y ***REMOVED***/dev.'
)
MSG_STALE_MR = """
Noté que este merge request está en WIP y sin actividad hace bastante tiempo.
Para evitar que quede obsoleto e inmergeable, estaría bueno mirarlo. Te
recomiendo proceder con alguna de estas acciones:

* Si ya está listo para mergear, sacale el `WIP: ` del título y esperá a que
  reciba feedback
* Si se trata de un merge request experimental o pensado a largo plazo, cambiá
  el nombre del source branch de `tkt_....` a `exp_....` para que lo tenga en
  cuenta
* Si te parece que los cambios no son más requeridos, cerrá el merge request
* En caso contrario, hacé las modificaciones que sean necesarias y sacarle
  el WIP
* También se puede agregar el label especial `no-me-apures` para que no vuelva
  a mostrar este mensaje en este merge request. Esto es una inhibición de mis
  gorra-poderes así que prefiero que no se abuse de esta opción
"""
MSG_MR_OLD_MEMBER = (
    '@***REMOVED***: Este merge request no está listo y está asignado a un usuario '
    'que ya no forma parte del equipo. Habría que cerrarlo o reasignárselo a '
    'alguien más'
)

# Define inactivity as a merge request whose last commit is older than
# now() - inactivity_time
inactivity_time = datetime.timedelta(days=30)

# Time to wait until a new message indicating the MR is stale is created
stale_mr_message_interval = datetime.timedelta(days=7)

# Time to wait until a new message indicating the MR is stale is created
decision_issue_message_interval = datetime.timedelta(days=0)


__other_regex = {
    '***REMOVED***': r'***REMOVED***'
}
regex_dict = defaultdict(lambda: r'^(?:tkt|mig|sup|exp)_(\d+|y2k)[-_].+', __other_regex)

