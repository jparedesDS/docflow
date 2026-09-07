import re
import pandas as pd
from datetime import datetime

# ═══════════════════════════════════════════════════════
#  MAPPINGS COMPARTIDOS (migrados de DocuControl)
# ═══════════════════════════════════════════════════════

# PO → Nº Pedido (PRODOC/ACONEX)
PRODOC_PO_MAP = {
    "7000100030": "P-26/008", "7000100060": "P-26/010",
    "7000100040": "P-26/009", "7000100050": "P-26/011",
    "1000100004": "P-26/303", "7000100005": "P-26/012",
    "7000100080": "P-26/013", "7000100013": "P-26/014",
    "7000100070": "P-26/015", "7000100014": "P-26/016",
    "7000100015": "P-26/017",
}

# PO → Nº Pedido (SENDOC)
SENDOC_PO_MAP = {
    "P1Q0000001-PF-V": "P-26/018-S00",
}

# Package → Nº Pedido (ACONEX)
ACONEX_PO_MAP = {
    "2201AA00A0-1100-3000": "P-26/019",
}

# AYESA: referencia del asunto ("Documentos de <ref>") → Nº PO del ERP.
# El portal AYESA usa su propia numeración (proyecto 2206 / ref 3000000001-...),
# que NO está en data_erp; este mapa enlaza esa referencia con el PO real, y de
# ahí se resuelve el Nº Pedido vía ERP. Añadir una entrada por pedido AYESA nuevo.
AYESA_REF_PO_MAP = {
    "3000000001-1100-3000": "7000100020",  # P-26/023 · ORIFICIOS Y REF033 DE RESTRICCIÓN
}

# AYESA: código de tipo (en el código de doc de cliente, p.ej. ...-DL-001) →
# valor de "Tipo Doc." del ERP, para emparejar el documento del email con el
# documento del pedido y rellenar su Nº Doc. EIPSA.
AYESA_DOC_TYPE_TO_ERP = {
    "DL": "VDDL", "LIS": "VDDL", "VDDL": "VDDL", "IND": "VDDL",
    "ITP": "PPI", "PLN": "PPI", "PPI": "PPI",
    "PLA": "Programa", "PRG": "Programa",
    "CAL": "Cálculos", "ESP": "Cálculos",
    "PLG": "Planos", "DWG": "Planos",
    "CER": "Certificados", "NACE": "Certificados",
    "DOS": "Dossier", "DD": "Dossier",
    "PRC": "Procedimientos", "NDE": "Procedimientos",
    "PRC0": "Packing",
}

# Project key → Nº Pedido (DOCUMENT SPACE / HEC)
DOCSPACE_PO_MAP = {
    "PRY&001": "P-26/002",
}
DOCSPACE_SUPP_MAP = {
    "PRY&001": "S00",
}
DOCSPACE_MATERIAL_MAP = {
    "PRY&001": "REF016",
}

# PO → Material
PRODOC_MATERIAL_MAP = {
    "7000100030": "REF016", "7000100060": "REF034",
    "7000100040": "REF034", "7000100050": "REF033",
}

SENDOC_MATERIAL_MAP = {
    "P1Q0000001-PF-V": "REF034",
}

GAIA_MATERIAL_MAP = {
    "100000C": "REF016", "7000100060": "REF034",
}

# Doc type code → Nombre español
DOC_TYPE_MAP = {
    "PLG": "Planos", "DWG": "Planos", "DRAWINGS": "Planos",
    "CAL": "Cálculos", "ESP": "Cálculos y Planos",
    "CER": "Certificado", "NACE": "Certificado",
    "DOS": "Dossier", "DD": "Dossier",
    "LIS": "Listado", "LIST": "Listado", "VDB": "Listado",
    "VDDL": "Listado", "DL": "Listado",
    "ITP": "PPI", "PLN": "PPI",
    "PLA": "Programa", "PRG": "Programa",
    "PRC": "Procedimientos", "NDE": "Procedimientos", "PH": "Procedimientos",
    "MAN": "Manual", "PLD": "Nameplate",
    "CAT": "Catalogo", "SPL": "Repuestos",
    "WD": "Soldadura", "IND": "Indice",
}

# Tipo doc → Crítico
CRITICO_MAP = {
    "Planos": "Sí", "Cálculos": "Sí", "Cálculos y Planos": "Sí",
    "Manual": "Sí", "PPI": "Sí", "Catalogo": "Sí", "Listado": "Sí",
    "Certificado": "No", "Dossier": "No", "Procedimientos": "No",
    "Nameplate": "No", "Repuestos": "No", "Indice": "No",
    "Soldadura": "No",
}

# Status mappings por plataforma
ACONEX_STATUS_MAP = {
    "A - REJECTED": "Rechazado",
    "1 - WITH COMMENTS": "Com. Mayores",
    "2 - WITHOUT COMMENTS": "Aprobado",
    "2I - FOR INFORMATION ONLY": "Informativo",
    "3 - WITH MINOR COMMENTS": "Com. Menores",
}

SENDOC_STATUS_MAP = {
    "(COD 5)": "Rechazado",
    "2-REVIEW WITH COMMENTS (COD 2)": "Com. Menores",
    "1-NO COMMENTS (COD 1)": "Aprobado",
    "(COD 3)": "Com. Mayores",
    "4-INF ONLY (COD 4)": "Informativo",
}

GAIA_STATUS_MAP = {
    "Code 1": "Com. Mayores",
    "Code 2": "Com. Menores",
    "Code 3": "Aprobado",
    "Code 4": "Informativo",
    "Code 5": "Rechazado",
}

# PO (primeros 5 chars) → Cliente
PO_CLIENT_MAP = {
    '10004': 'TECHNIP/CLIENTE285',
    '10121': 'OMEGA', '10150': 'CLIENTE166',
    '10160': 'CLIENTE67', '10230': 'SIGMA',
    '10318': 'RAS CLIENTE291', '10330': 'NEW PTA COMPLEX',
    '10370': 'DELTA 3', '10380': 'OMEGA',
    '10400': 'OMEGA CLIENTE72', '10430': 'DELTA 4',
    '23222': 'CQP', '23262': 'Certificado',
    '33138': 'OMEGA', '70150': 'CLIENTE265',
    '70215': 'CFE CLIENTE190', '70225': 'CLIENTE41 CLIENTE315',
    '70230': 'CLIENTE41 CLIENTE126 CLIENTE210', '70240': 'CLIENTE41 SAN LUIS',
    '80057': 'BU CLIENTE131', '80091': 'CLIENTE287 CLIENTE93',
    '19085': 'ATLAS/CLIENTE287', '30011': 'REFINERIA DEL NORTE',
    '75001': 'OMEGA', '60001': 'ATLAS WOOD',
    '70112': 'ATLAS SAN CLIENTE243', '70801': 'ATLAS',
    '15282': 'CLIENTE24', 'T.206': 'ATLAS CLIENTE221',
    'BP-T2': 'CLIENTE53', 'EP24I': 'KAPPA/KAPPA',
    '49000': 'CLIENTE163/ACME', 'PO 15': 'CLIENTE24',
    'Q3710': 'CLIENTE154 INDUSTRIAL', 'RFQ 1': 'BU CLIENTE131',
    '70292': 'CLIENTE175', 'APEIS': 'CLIENTE171',
    '30012': 'REFINERIA DEL NORTE',
    'EC24T': 'KAPPA/KAPPA', '10735': 'CLIENTE280',
    '70700': 'ATLAS/WOOD', 'JUS&I': 'ACME/HYUNDAI',
    '70113': 'ATLAS', '10620': 'DELTABOP/TR',
    'ADI-2': 'TECHNIP/CLIENTE285', '10431': 'DELTAEPC4/TR',
    'PO P7': 'TECHNIP/ATLAS', '12574': 'CLIENTE13',
    '23000': 'TECHNIP/CLIENTE121',
    '45077': 'ACME PORTAL', '45000': 'AYESA/ATLAS',
    '30015': 'REFINERIA DEL NORTE', '19162': 'CLIENTE320/ACME',
    '48550': 'CLIENTE320/ACME', '20175': 'TECHNIP/ATLAS',
    'QR-DD': 'CLIENTE24/WOOD', 'RFPP-': 'CLIENTE140/ATLAS',
    '10120': 'TR/OMEGA', 'CLIENTE273': 'CLIENTE273/CLIENTE89',
    '41650': 'CLIENTE273/CLIENTE89', 'P-P0C': 'SACYR/ATLAS',
    'SEG/B': 'CLIENTE269/ACME', 'SEG /': 'CLIENTE269/ACME',
    '10002': 'ACME/NORTE', '45124': 'OMEGA/CLIENTE324',
    'O-23/': 'CLIENTE268/CLIENTE324', 'O-24/': 'SENER/CLIENTE125',
    'GAT22': 'SENER/CLIENTE125', '45126': 'OMEGA/CLIENTE324',
    'POPRI': 'ATLAS', '06000': 'ATLAS', '5040-': 'CLIENTE187',
    'PO 45': 'ACME', 'E2404': 'CLIENTE262', '5061-': 'CLIENTE187',
    '60002': 'ATLAS', 'TR-19': 'ATLAS', '19128': 'ATLAS',
    'D2632': 'ATLAS', '44000': 'CLIENTE217',
    'PE-47': 'CLIENTE295', '45131': 'CLIENTE325/CLIENTE121', 'EC25T': 'KAPPA/KAPPA',
    '45032': 'CLIENTE323', '46000': 'CLIENTE163', '30013': 'BP/TECHNIP',
    '19116': 'BP OIL',
    '2201B': 'ACONEX',
}

# Emails de responsables
_EMAIL_LB = 'persona@tuempresa.com'
_EMAIL_AC = 'persona@tuempresa.com'
_EMAIL_SS = 'persona@tuempresa.com'  # una comercial (ex-trabajadora) → sus proyectos pasaron a Luis Bravo
_EMAIL_JV = 'persona@tuempresa.com'
_EMAIL_CCH = 'persona@tuempresa.com'

# Nº Pedido → email responsable proyecto
RESPONSABLE_PEDIDO_MAP = {
    'P-26/101': _EMAIL_LB,
    'P-26/102': _EMAIL_LB, 'P-26/103': _EMAIL_LB, 'P-26/104': _EMAIL_AC, 'P-26/105': _EMAIL_AC,
    'P-26/106': _EMAIL_AC, 'P-26/107': _EMAIL_LB, 'P-26/108': _EMAIL_LB, 'P-26/109': _EMAIL_AC,
    'P-26/110': _EMAIL_LB, 'P-26/111': _EMAIL_AC, 'P-26/112': _EMAIL_LB, 'P-26/113': _EMAIL_AC,
    'P-26/114': _EMAIL_LB, 'P-26/115': _EMAIL_AC, 'P-26/116': _EMAIL_LB, 'P-26/117': _EMAIL_LB,
    'P-26/118': _EMAIL_AC, 'P-26/119': _EMAIL_AC, 'P-26/120': _EMAIL_AC, 'P-26/121': _EMAIL_LB,
    'P-26/122': _EMAIL_AC, 'P-26/123': _EMAIL_AC, 'P-26/124': _EMAIL_AC, 'P-26/125': _EMAIL_AC,
    'P-26/126': _EMAIL_LB, 'P-26/127': _EMAIL_LB, 'P-26/128': _EMAIL_LB, 'P-26/129': _EMAIL_AC,
    'P-26/130': _EMAIL_LB, 'P-26/131': _EMAIL_LB, 'P-26/132': _EMAIL_AC, 'P-26/133': _EMAIL_AC,
    'P-26/134': _EMAIL_LB, 'P-26/135': _EMAIL_LB, 'P-26/136': _EMAIL_AC, 'P-26/137': _EMAIL_AC,
    'P-26/138': _EMAIL_LB, 'P-26/139': _EMAIL_AC, 'P-26/140': _EMAIL_AC, 'P-26/141': _EMAIL_LB,
    'P-26/142': _EMAIL_LB, 'P-26/143': _EMAIL_AC, 'P-26/144': _EMAIL_AC, 'P-26/145': _EMAIL_AC,
    'P-26/146': _EMAIL_AC, 'P-26/147': _EMAIL_AC, 'P-26/148': _EMAIL_SS, 'P-26/149': _EMAIL_LB,
    'P-26/150': _EMAIL_LB, 'P-26/151': _EMAIL_LB, 'P-26/152': _EMAIL_AC, 'P-26/153': _EMAIL_AC,
    'P-26/154': _EMAIL_SS, 'P-26/155': _EMAIL_SS, 'P-26/156': _EMAIL_AC, 'P-26/157': _EMAIL_AC,
    'P-26/158': _EMAIL_AC, 'P-26/159': _EMAIL_AC, 'P-26/160': _EMAIL_AC, 'P-26/161': _EMAIL_AC,
    'P-26/162': _EMAIL_LB, 'P-26/163': _EMAIL_SS, 'P-26/164': _EMAIL_SS, 'P-26/165': _EMAIL_LB,
    'P-26/166': _EMAIL_AC, 'P-26/167': _EMAIL_AC, 'P-26/168': _EMAIL_AC, 'P-26/169': _EMAIL_AC,
    'P-26/170': _EMAIL_AC, 'P-26/171': _EMAIL_SS, 'P-26/172': _EMAIL_AC, 'P-26/173': _EMAIL_LB,
    'P-26/174': _EMAIL_AC, 'P-26/175': _EMAIL_LB, 'P-26/176': _EMAIL_SS, 'P-26/177': _EMAIL_LB,
    'P-26/178': _EMAIL_AC, 'P-26/179': _EMAIL_AC, 'P-26/180': _EMAIL_AC, 'P-26/181': _EMAIL_SS,
    'P-26/182': _EMAIL_AC, 'P-26/183': _EMAIL_LB, 'P-26/184': _EMAIL_AC, 'P-26/185': _EMAIL_LB,
    'P-26/186': _EMAIL_LB, 'P-26/187': _EMAIL_LB, 'P-26/188': _EMAIL_LB, 'P-26/189': _EMAIL_LB,
    'P-26/190': _EMAIL_LB, 'P-26/191': _EMAIL_LB, 'P-26/192': _EMAIL_LB, 'P-26/193': _EMAIL_LB,
    'P-26/194': _EMAIL_LB, 'P-26/195': _EMAIL_LB, 'P-26/196': _EMAIL_LB, 'P-26/197': _EMAIL_LB,
    'P-26/198': _EMAIL_LB, 'P-26/199': _EMAIL_LB, 'P-26/200': _EMAIL_LB, 'P-26/201': _EMAIL_LB,
    'P-26/202': _EMAIL_LB, 'P-26/203': _EMAIL_LB, 'P-26/204': _EMAIL_LB, 'P-26/205': _EMAIL_LB,
    'P-26/206': _EMAIL_LB,
    'P-26/207': _EMAIL_LB, 'P-26/208': _EMAIL_LB, 'P-26/209': _EMAIL_LB, 'P-26/210': _EMAIL_AC,
    'P-26/211': _EMAIL_AC, 'P-26/212': _EMAIL_AC, 'P-26/213': _EMAIL_LB, 'P-26/214': _EMAIL_AC,
    'P-26/215': _EMAIL_AC, 'P-26/216': _EMAIL_AC, 'P-26/217': _EMAIL_SS, 'P-26/218': _EMAIL_AC,
    'P-26/219': _EMAIL_LB, 'P-26/220': _EMAIL_SS, 'P-26/221': _EMAIL_AC, 'P-26/222': _EMAIL_AC,
    'P-26/223': _EMAIL_SS, 'P-26/224': _EMAIL_AC, 'P-26/225': _EMAIL_LB, 'P-26/226': _EMAIL_AC,
    'P-26/227': _EMAIL_LB, 'P-26/228': _EMAIL_LB, 'P-26/229': _EMAIL_AC, 'P-26/230': _EMAIL_LB,
    'P-26/231': _EMAIL_LB, 'P-26/232': _EMAIL_SS, 'P-26/414': _EMAIL_LB, 'P-26/234': _EMAIL_LB,
    'P-26/235': _EMAIL_LB, 'P-26/236': _EMAIL_LB, 'P-26/237': _EMAIL_AC, 'P-26/238': _EMAIL_AC,
    'P-26/239': _EMAIL_AC, 'P-26/240': _EMAIL_SS, 'P-26/241': _EMAIL_AC, 'P-26/242': _EMAIL_AC,
    'P-26/412': _EMAIL_LB, 'P-26/244': _EMAIL_LB, 'P-26/245': _EMAIL_LB, 'P-26/246': _EMAIL_AC,
    'P-26/247': _EMAIL_AC, 'P-26/248': _EMAIL_LB, 'P-26/249': _EMAIL_LB, 'P-26/250': _EMAIL_LB,
    'P-26/251': _EMAIL_AC, 'P-26/252': _EMAIL_SS, 'P-26/253': _EMAIL_AC, 'P-26/254': _EMAIL_SS,
    'P-26/255': _EMAIL_LB, 'P-26/256': _EMAIL_LB, 'P-26/257': _EMAIL_AC, 'P-26/258': _EMAIL_AC,
    'P-26/259': _EMAIL_AC, 'P-26/260': _EMAIL_AC, 'P-26/261': _EMAIL_AC, 'P-26/262': _EMAIL_SS,
    'P-26/263': _EMAIL_LB, 'P-26/264': _EMAIL_AC, 'P-26/265': _EMAIL_LB, 'P-26/266': _EMAIL_AC,
    'P-26/267': _EMAIL_LB, 'P-26/268': _EMAIL_AC, 'P-26/269': _EMAIL_AC, 'P-26/270': _EMAIL_AC,
    'P-26/271': _EMAIL_AC, 'P-26/272': _EMAIL_AC, 'P-26/273': _EMAIL_AC, 'P-26/274': _EMAIL_AC,
    'P-26/275': _EMAIL_AC, 'P-26/276': _EMAIL_AC, 'P-26/277': _EMAIL_AC, 'P-26/278': _EMAIL_LB,
    'P-26/279': _EMAIL_AC, 'P-26/280': _EMAIL_SS, 'P-26/281': _EMAIL_LB, 'P-26/282': _EMAIL_LB,
    'P-26/283': _EMAIL_AC, 'P-26/284': _EMAIL_AC, 'P-26/285': _EMAIL_LB, 'P-26/286': _EMAIL_AC,
    'P-26/287': _EMAIL_AC, 'P-26/288': _EMAIL_AC, 'P-26/289': _EMAIL_AC, 'P-26/290': _EMAIL_AC,
    'P-26/291': _EMAIL_AC, 'P-26/292': _EMAIL_AC, 'P-26/011': _EMAIL_AC, 'P-26/294': _EMAIL_AC,
    'P-26/295': _EMAIL_SS, 'P-26/296': _EMAIL_AC, 'P-26/297': _EMAIL_AC, 'P-26/298': _EMAIL_LB,
    'P-26/299': _EMAIL_AC, 'P-26/300': _EMAIL_LB, 'P-26/301': _EMAIL_AC, 'P-26/302': _EMAIL_AC,
    'P-26/303': _EMAIL_AC, 'P-26/304': _EMAIL_LB, 'P-26/305': _EMAIL_LB, 'P-26/306': _EMAIL_AC,
    'P-26/307': _EMAIL_AC, 'P-26/308': _EMAIL_AC, 'P-26/309': _EMAIL_LB, 'P-26/310': _EMAIL_AC,
    'P-26/311': _EMAIL_SS,
    'P-26/312': _EMAIL_LB, 'P-26/313': _EMAIL_LB, 'P-26/314': _EMAIL_LB,
    'P-26/315': _EMAIL_AC, 'P-26/316': _EMAIL_AC, 'P-26/012': _EMAIL_AC, 'P-26/318': _EMAIL_AC,
    'P-26/319': _EMAIL_AC, 'P-26/320': _EMAIL_AC, 'P-26/321': _EMAIL_AC, 'P-26/322': _EMAIL_AC,
    'P-26/323': _EMAIL_SS, 'P-26/324': _EMAIL_AC, 'P-26/325': _EMAIL_AC, 'P-26/326': _EMAIL_SS,
    'P-26/327': _EMAIL_AC, 'P-26/328': _EMAIL_AC, 'P-26/329': _EMAIL_AC, 'P-26/330': _EMAIL_AC,
    'P-26/331': _EMAIL_AC, 'P-26/332': _EMAIL_AC, 'P-26/333': _EMAIL_AC, 'P-26/013': _EMAIL_AC,
    'P-26/335': _EMAIL_AC, 'P-26/336': _EMAIL_AC, 'P-26/337': _EMAIL_AC, 'P-26/338': _EMAIL_AC,
    'P-26/339': _EMAIL_AC, 'P-26/340': _EMAIL_AC, 'P-26/341': _EMAIL_AC, 'P-26/342': _EMAIL_AC,
    'P-26/343': _EMAIL_AC, 'P-26/344': _EMAIL_AC, 'P-26/345': _EMAIL_AC, 'P-26/346': _EMAIL_AC,
    'P-26/347': _EMAIL_AC, 'P-26/348': _EMAIL_AC, 'P-26/349': _EMAIL_AC, 'P-26/350': _EMAIL_AC,
    'P-26/351': _EMAIL_AC, 'P-26/352': _EMAIL_AC, 'P-26/353': _EMAIL_AC, 'P-26/354': _EMAIL_AC,
    'P-26/014': _EMAIL_AC, 'P-26/356': _EMAIL_AC, 'P-26/357': _EMAIL_AC, 'P-26/358': _EMAIL_AC,
    'P-26/359': _EMAIL_AC, 'P-26/360': _EMAIL_AC, 'P-26/015': _EMAIL_AC, 'P-26/362': _EMAIL_AC,
    'P-26/363': _EMAIL_AC, 'P-26/364': _EMAIL_AC, 'P-26/010': _EMAIL_AC, 'P-26/366': _EMAIL_AC,
    'P-26/367': _EMAIL_AC, 'P-26/368': _EMAIL_AC, 'P-26/016': _EMAIL_AC, 'P-26/370': _EMAIL_AC,
    'P-26/017': _EMAIL_AC, 'P-26/372': _EMAIL_AC, 'P-26/373': _EMAIL_AC, 'P-26/374': _EMAIL_AC,
    'P-26/375': _EMAIL_AC, 'P-26/376': _EMAIL_AC, 'P-26/001': _EMAIL_LB, 'P-26/378': _EMAIL_AC,
    'P-26/379': _EMAIL_AC, 'P-26/380': _EMAIL_LB, 'P-26/002': _EMAIL_LB, 'P-26/382': _EMAIL_AC,
    'P-26/383': _EMAIL_AC, 'P-26/009': _EMAIL_AC, 'P-26/385': _EMAIL_AC, 'P-26/386': _EMAIL_AC,
    'P-26/387': _EMAIL_AC, 'P-26/388': _EMAIL_AC, 'P-26/389': _EMAIL_AC, 'P-26/390': _EMAIL_SS,
    'P-26/391': _EMAIL_SS, 'P-26/392': _EMAIL_AC, 'P-26/393': _EMAIL_AC, 'P-26/394': _EMAIL_AC,
    'P-26/395': _EMAIL_AC, 'P-26/396': _EMAIL_LB, 'P-26/397': _EMAIL_CCH, 'P-26/024': _EMAIL_AC,
    'P-26/399': _EMAIL_AC, 'P-26/400': _EMAIL_AC, 'P-26/401': _EMAIL_AC, 'P-26/008': _EMAIL_AC,
    'P-26/403': _EMAIL_SS, 'P-26/404': _EMAIL_LB, 'P-26/026': _EMAIL_LB, 'P-26/406': _EMAIL_AC,
    'P-26/407': _EMAIL_CCH, 'P-26/408': _EMAIL_AC, 'P-26/409': _EMAIL_CCH, 'P-26/410': _EMAIL_CCH,
    'P-26/411': _EMAIL_SS,
    'P-26/412': _EMAIL_AC, 'P-26/413': _EMAIL_AC, 'P-26/414': _EMAIL_SS,
    'P-26/415': _EMAIL_AC, 'P-26/416': _EMAIL_SS, 'P-26/417': _EMAIL_CCH, 'P-26/418': _EMAIL_SS,
    'P-26/419': _EMAIL_AC, 'P-26/018': _EMAIL_AC, 'P-26/421': _EMAIL_AC, 'P-26/422': _EMAIL_AC,
    'P-26/423': _EMAIL_AC, 'P-26/424': _EMAIL_AC, 'P-26/425': _EMAIL_AC, 'P-26/426': _EMAIL_SS,
    'P-26/427': _EMAIL_AC, 'P-26/415': _EMAIL_AC, 'P-26/429': _EMAIL_AC, 'P-26/430': _EMAIL_CCH,
    'P-26/431': _EMAIL_AC, 'P-26/432': _EMAIL_AC, 'P-26/433': _EMAIL_AC, 'P-26/413': _EMAIL_SS,
    'P-26/435': _EMAIL_SS, 'P-26/436': _EMAIL_AC, 'P-26/437': _EMAIL_LB, 'P-26/438': _EMAIL_LB,
    'P-26/439': _EMAIL_LB, 'P-26/440': _EMAIL_AC, 'P-26/441': _EMAIL_SS, 'P-26/442': _EMAIL_SS,
    'P-26/443': _EMAIL_AC, 'P-26/444': _EMAIL_AC, 'P-26/445': _EMAIL_CCH, 'P-26/446': _EMAIL_CCH,
    'P-26/447': _EMAIL_LB, 'P-26/019': _EMAIL_AC, 'P-26/449': _EMAIL_AC, 'P-26/450': _EMAIL_AC,
    'P-26/451': _EMAIL_SS, 'P-26/452': _EMAIL_AC, 'P-26/453': _EMAIL_AC, 'P-26/454': _EMAIL_SS,
    'P-26/455': _EMAIL_SS, 'P-26/456': _EMAIL_LB, 'P-26/457': _EMAIL_LB, 'P-26/458': _EMAIL_AC,
    'P-26/459': _EMAIL_CCH, 'P-26/460': _EMAIL_CCH, 'P-26/461': _EMAIL_LB, 'P-26/462': _EMAIL_AC,
    'P-26/463': _EMAIL_SS, 'P-26/464': _EMAIL_AC, 'P-26/465': _EMAIL_LB, 'P-26/466': _EMAIL_AC,
    'P-26/467': _EMAIL_AC, 'P-26/468': _EMAIL_AC, 'P-26/469': _EMAIL_AC, 'P-26/470': _EMAIL_LB,
    'P-26/471': _EMAIL_AC, 'P-26/472': _EMAIL_AC, 'P-26/473': _EMAIL_AC, 'P-26/474': _EMAIL_LB,
    'P-26/475': _EMAIL_AC, 'P-26/476': _EMAIL_AC, 'P-26/477': _EMAIL_CCH, 'P-26/478': _EMAIL_AC,
    'P-26/479': _EMAIL_SS, 'P-26/480': _EMAIL_AC, 'P-26/481': _EMAIL_CCH, 'P-26/482': _EMAIL_AC,
    'P-26/483': _EMAIL_SS, 'P-26/484': _EMAIL_AC, 'P-26/485': _EMAIL_CCH, 'P-25/075': _EMAIL_AC,
    'P-25/076': _EMAIL_SS, 'P-25/077': _EMAIL_AC, 'P-25/078': _EMAIL_CCH, 'P-25/079': _EMAIL_AC,
    'P-25/080': _EMAIL_SS, 'P-25/081': _EMAIL_AC, 'P-25/082': _EMAIL_CCH, 'P-25/083': _EMAIL_AC,
    'P-25/084': _EMAIL_SS, 'P-25/085': _EMAIL_AC, 'P-25/086': _EMAIL_CCH, 'P-25/087': _EMAIL_AC,
    'P-25/088': _EMAIL_SS, 'P-25/089': _EMAIL_AC, 'P-25/090': _EMAIL_CCH, 'P-25/091': _EMAIL_AC,
    'P-25/092': _EMAIL_SS, 'P-25/093': _EMAIL_AC, 'P-25/094': _EMAIL_CCH, 'P-25/095': _EMAIL_AC,
    'P-25/096': _EMAIL_SS, 'P-25/097': _EMAIL_AC, 'P-25/098': _EMAIL_CCH, 'P-25/099': _EMAIL_AC,
    'P-26/001': _EMAIL_SS, 'P-26/002': _EMAIL_AC, 'P-26/023': _EMAIL_CCH, 'P-26/004': _EMAIL_AC,
    'P-26/005': _EMAIL_SS, 'P-26/006': _EMAIL_AC, 'P-26/007': _EMAIL_CCH, 'P-26/008': _EMAIL_AC,
    'P-26/009': _EMAIL_SS, 'P-26/010': _EMAIL_AC, 'P-26/011': _EMAIL_CCH, 'P-26/012': _EMAIL_AC,
    'P-26/013': _EMAIL_SS, 'P-26/014': _EMAIL_AC, 'P-26/015': _EMAIL_CCH, 'P-26/016': _EMAIL_AC,
    'P-26/017': _EMAIL_SS, 'P-26/018': _EMAIL_AC, 'P-26/019': _EMAIL_CCH, 'P-26/020': _EMAIL_AC,
    'P-26/022': _EMAIL_SS, 'P-26/022': _EMAIL_AC, 'P-26/023': _EMAIL_CCH, 'P-26/024': _EMAIL_AC,
    'P-26/025': _EMAIL_SS, 'P-26/026': _EMAIL_AC, 'P-26/006': _EMAIL_LB, 'P-26/028': _EMAIL_AC,
    'P-26/029': _EMAIL_AC, 'P-26/007': _EMAIL_AC, 'P-26/005': _EMAIL_AC, 'P-26/032': _EMAIL_AC,
    'P-26/033': _EMAIL_SS, 'P-26/034': _EMAIL_AC, 'P-26/035': _EMAIL_CCH, 'P-26/036': _EMAIL_AC,
}

# Email → iniciales para columna Responsable
EMAIL_TO_INITIALS = {
    'persona@tuempresa.com': 'LB',
    'persona@tuempresa.com': 'AC',
    'persona@tuempresa.com': 'CCH',
    'persona@tuempresa.com': 'JV',
}

# Doc type code → email CC responsable técnico
DOC_TYPE_EMAIL_MAP = {
    'CER': _EMAIL_JV, 'LIS': _EMAIL_JV, 'PRC': _EMAIL_JV,
    'MAN': _EMAIL_JV, 'CAT': _EMAIL_JV, 'DOS': _EMAIL_JV,
    'SPL': _EMAIL_JV, 'DD': _EMAIL_JV, 'SP': _EMAIL_JV,
}

# Destinatarios fijos
DEFAULT_TO = ["persona@tuempresa.com"]
DEFAULT_CC = ["persona@tuempresa.com", "persona@tuempresa.com"]


# ═══════════════════════════════════════════════════════
#  FUNCIONES COMPARTIDAS
# ═══════════════════════════════════════════════════════

def apply_po_mapping(df, po_col, mapping):
    df["Nº Pedido"] = df[po_col].astype(str).str.strip().map(mapping).fillna(df[po_col])
    return df


def apply_material_mapping(df, po_col, mapping):
    df["Material"] = df[po_col].astype(str).str.strip().map(mapping).fillna(df[po_col])
    return df


def apply_doc_type(df, code_col):
    df["Tipo de documento"] = df[code_col].map(DOC_TYPE_MAP)
    return df


def apply_critico(df):
    df["Crítico"] = df["Tipo de documento"].map(CRITICO_MAP).fillna("No")
    return df


def apply_fecha(df, received_time_str):
    df["Fecha"] = pd.to_datetime(received_time_str, dayfirst=True)
    return df


def fill_supp_nulls(df):
    if "Supp." in df.columns:
        df["Supp."] = df["Supp."].fillna("S00")
    else:
        df["Supp."] = "S00"
    return df


def identify_client(po: str) -> str:
    """Identifica cliente a partir de los primeros 5 caracteres del PO."""
    if not po or len(po) < 5:
        return ""
    return PO_CLIENT_MAP.get(po[:5], "")


def get_responsable_email(numero_pedido: str) -> str | None:
    """Devuelve email del responsable del proyecto por Nº Pedido."""
    for key, email in RESPONSABLE_PEDIDO_MAP.items():
        if key in str(numero_pedido):
            return email
    return None


def get_responsable_initials(numero_pedido: str) -> str:
    """Devuelve iniciales del responsable (LB, AC, etc.) por Nº Pedido."""
    email = get_responsable_email(numero_pedido)
    if email:
        return EMAIL_TO_INITIALS.get(email, "")
    return ""


def get_doc_type_cc(doc_type_code: str) -> str | None:
    """Devuelve email CC del responsable técnico por código de tipo doc."""
    if not doc_type_code:
        return None
    return DOC_TYPE_EMAIL_MAP.get(doc_type_code.upper(), None)


def compute_recipients(df) -> tuple[list[str], list[str]]:
    """Calcula To y CC dinámicos basándose en Nº Pedido y tipo doc."""
    to_set = set(DEFAULT_TO)
    cc_set = set(DEFAULT_CC)

    if len(df) > 0:
        first = df.iloc[0]
        n_pedido = str(first.get("Nº Pedido", ""))
        resp_email = get_responsable_email(n_pedido)
        if resp_email:
            to_set.add(resp_email)

        # Buscar CC por tipo de documento (invertir DOC_TYPE_MAP)
        tipo_to_codes = {}
        for code, nombre in DOC_TYPE_MAP.items():
            tipo_to_codes.setdefault(nombre, []).append(code)

        for _, row in df.iterrows():
            # Intentar con _doc_code primero, luego buscar por Tipo de documento
            doc_code = str(row.get("_doc_code", ""))
            if doc_code:
                cc_email = get_doc_type_cc(doc_code)
                if cc_email:
                    cc_set.add(cc_email)
                    continue
            tipo = str(row.get("Tipo de documento", ""))
            for code in tipo_to_codes.get(tipo, []):
                cc_email = get_doc_type_cc(code)
                if cc_email:
                    cc_set.add(cc_email)
                    break

    return sorted(to_set), sorted(cc_set)


def _is_dark_color(hex_color: str) -> bool:
    """Devuelve True si el color hex tiene luminancia baja (fondo oscuro)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return False
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return False
    # Luminancia perceptual (rec. 709)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return lum < 128


def _load_logo_b64(bg_color: str | None = None) -> str | None:
    """Carga el logo EIPSA como base64 (PNG), profesional sobre cualquier fondo.

    Estrategia:
    1. Carga el PNG con alpha.
    2. Elimina fondo blanco/casi-blanco → transparente (limpia el halo).
    3. Si `bg_color` es oscuro: convierte la silueta del logo a BLANCO
       (convención corporativa estándar — version 'reverse' del logo).
       Esto garantiza máximo contraste sobre header navy/dark.
       Si `bg_color` es claro o None: preserva los colores originales.
    4. Compone sobre `bg_color` si se proporciona, devolviendo PNG opaco.
    """
    import base64, os, io
    try:
        from PIL import Image
    except ImportError:
        Image = None

    candidates = [
        r"M:\Comunes\JOSE\07 LOGOTIPOS\EIPSA NEW LOGO, CORTADO.png",
        os.path.join(os.path.dirname(__file__), "..", "..", "assets", "eipsa_logo.png"),
    ]
    TARGET_HEIGHT = 80

    invert_to_white = bool(bg_color and _is_dark_color(bg_color))

    for path in candidates:
        try:
            with open(path, "rb") as f:
                raw = f.read()

            if Image is None:
                return base64.b64encode(raw).decode()

            img = Image.open(io.BytesIO(raw)).convert("RGBA")

            # 1. Limpiar fondo blanco/casi-blanco + (opcional) invertir silueta a blanco
            WHITE_THRESH = 230
            data = img.getdata()
            new_data = []
            for r, g, b, a in data:
                if r > WHITE_THRESH and g > WHITE_THRESH and b > WHITE_THRESH:
                    # Fondo blanco → transparente
                    new_data.append((255, 255, 255, 0))
                elif invert_to_white and a > 0:
                    # Sobre fondo oscuro: mapear cualquier color del logo a blanco
                    # preservando el alpha del original (mantiene anti-aliasing limpio)
                    new_data.append((255, 255, 255, a))
                else:
                    new_data.append((r, g, b, a))
            img.putdata(new_data)

            # 2. Redimensionar manteniendo proporción
            ratio = TARGET_HEIGHT / img.height
            new_size = (max(1, int(img.width * ratio)), TARGET_HEIGHT)
            img = img.resize(new_size, Image.LANCZOS)

            # 3. Composite sobre color del header (sin alpha)
            if bg_color:
                bg = Image.new("RGB", img.size, bg_color)
                bg.paste(img, mask=img.split()[3])
                img = bg

            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            continue
    return None


def build_notification_html(df_info_dict, df_docs, deadline_date):
    """Genera el HTML del email de notificación — diseño corporativo EIPSA."""
    from collections import Counter

    # ── Paleta EIPSA ──
    NAVY   = "#1B3A5C"   # azul corporativo EIPSA
    CYAN   = "#00AEEF"   # azul claro del logo

    # Colores por estado
    STATUS_BG   = {"Rechazado": "#FFEBEE", "Com. Menores": "#FFF3E0", "Com. Mayores": "#FCE4EC",
                   "Aprobado": "#E8F5E9", "Comentado": "#F3E5F5", "Informativo": "#E3F2FD", "Eliminado": "#F5F5F5"}
    STATUS_TEXT = {"Rechazado": "#C62828", "Com. Menores": "#E65100", "Com. Mayores": "#AD1457",
                   "Aprobado": "#2E7D32", "Comentado": "#6A1B9A", "Informativo": "#1565C0", "Eliminado": "#757575"}
    STATUS_DOT  = {"Rechazado": "#E53935", "Com. Menores": "#FB8C00", "Com. Mayores": "#EC407A",
                   "Aprobado": "#43A047", "Comentado": "#AB47BC", "Informativo": "#1E88E5", "Eliminado": "#BDBDBD"}

    # ── Fecha límite ──
    deadline_str = deadline_date.strftime("%d de %B de %Y").replace(
        "January","enero").replace("February","febrero").replace("March","marzo").replace("April","abril").replace(
        "May","mayo").replace("June","junio").replace("July","julio").replace("August","agosto").replace(
        "September","septiembre").replace("October","octubre").replace("November","noviembre").replace("December","diciembre")

    # ── Logo: compuesto sobre el navy del header en backend (PIL), sin caja ──
    logo_b64 = _load_logo_b64(bg_color=NAVY)
    if logo_b64:
        logo_html = (
            f'<img src="data:image/png;base64,{logo_b64}" alt="EIPSA" '
            f'style="display:block;height:34px;width:auto;border:0;outline:0;" />'
        )
    else:
        # Fallback texto si no hay logo disponible
        logo_html = (
            f'<span style="font-size:18px;font-weight:800;color:#FFFFFF;'
            f'letter-spacing:1.2px;">EIPSA</span>'
        )

    # ── Info del pedido: tarjetas en grid 3 columnas ──
    items = [(k, v) for k, v in df_info_dict.items() if v]
    info_rows_html = ""
    for i in range(0, len(items), 3):
        chunk = items[i:i+3]
        cells = ""
        for k, v in chunk:
            cells += (
                f'<td style="padding:0 6px 12px;width:33%;">'
                f'<table cellpadding="0" cellspacing="0" style="width:100%;background:#F8FAFF;'
                f'border:1px solid #DDE3F5;border-radius:6px;">'
                f'<tr><td style="padding:10px 14px;border-left:3px solid {CYAN};">'
                f'<p style="margin:0;font-size:10px;font-weight:700;color:{CYAN};text-transform:uppercase;'
                f'letter-spacing:0.06em;">{k}</p>'
                f'<p style="margin:3px 0 0;font-size:13px;font-weight:700;color:{NAVY};">{v}</p>'
                f'</td></tr></table></td>'
            )
        # Rellenar celdas vacías si el chunk es < 3
        for _ in range(3 - len(chunk)):
            cells += '<td style="padding:0 6px 12px;width:33%;"></td>'
        info_rows_html += f'<tr>{cells}</tr>'

    # ── Tabla de documentos ──
    cols = ["Doc. Cliente", "Título", "Rev.", "Estado"]
    available_cols = [c for c in cols if c in df_docs.columns]

    th_style = (f"background:{NAVY};color:#FFFFFF;padding:10px 14px;font-size:10px;font-weight:700;"
                f"letter-spacing:0.06em;text-transform:uppercase;text-align:left;")
    header_cells = "".join(f'<th style="{th_style}">{c}</th>' for c in available_cols)

    doc_rows = ""
    for i, (_, row) in enumerate(df_docs.iterrows()):
        estado = str(row.get("Estado", ""))
        bg_row = "#F8FAFF" if i % 2 == 0 else "#FFFFFF"
        cells = ""
        for c in available_cols:
            val = str(row.get(c, "") or "—")
            if c == "Estado":
                sbg  = STATUS_BG.get(estado, "#F5F5F5")
                stxt = STATUS_TEXT.get(estado, "#424242")
                sdot = STATUS_DOT.get(estado, "#BDBDBD")
                cells += (
                    f'<td style="padding:10px 14px;border-bottom:1px solid #EEF2F7;">'
                    f'<span style="display:inline-flex;align-items:center;gap:5px;padding:4px 10px;'
                    f'border-radius:20px;background:{sbg};color:{stxt};font-size:11px;font-weight:700;">'
                    f'<span style="width:6px;height:6px;border-radius:50%;background:{sdot};flex-shrink:0;"></span>'
                    f'{val}</span></td>'
                )
            elif c == "Rev.":
                cells += (
                    f'<td style="padding:10px 14px;border-bottom:1px solid #EEF2F7;text-align:center;">'
                    f'<span style="color:#E53935;font-size:12px;font-weight:700;">{val}</span></td>'
                )
            elif c == "Doc. Cliente":
                cells += (
                    f'<td style="padding:10px 14px;border-bottom:1px solid #EEF2F7;'
                    f'font-family:\'Courier New\',monospace;font-size:11px;color:#37474F;white-space:nowrap;">{val}</td>'
                )
            else:
                cells += (
                    f'<td style="padding:10px 14px;border-bottom:1px solid #EEF2F7;'
                    f'font-size:12px;color:#37474F;line-height:1.5;">{val}</td>'
                )
        doc_rows += f'<tr style="background:{bg_row};">{cells}</tr>'

    # ── Resumen de estados ──
    estado_counts = Counter(str(row.get("Estado", "")) for _, row in df_docs.iterrows())
    summary_badges = ""
    for estado, count in estado_counts.items():
        sbg  = STATUS_BG.get(estado, "#F5F5F5")
        stxt = STATUS_TEXT.get(estado, "#424242")
        sdot = STATUS_DOT.get(estado, "#BDBDBD")
        summary_badges += (
            f'<span style="display:inline-flex;align-items:center;gap:5px;padding:5px 12px;'
            f'border-radius:20px;background:{sbg};color:{stxt};font-size:12px;font-weight:700;margin-right:8px;">'
            f'<span style="width:8px;height:8px;border-radius:50%;background:{sdot};"></span>'
            f'{count} {estado}</span>'
        )

    n_docs = len(df_docs)
    doc_label = "Documento devuelto" if n_docs == 1 else "Documentos devueltos"

    # ── Preheader (preview text en Outlook) ──
    _pedido = df_info_dict.get("Nº Pedido", "") or ""
    _cliente = df_info_dict.get("Cliente", "") or ""
    _estado_principal = estado_counts.most_common(1)[0][0] if estado_counts else ""
    preheader_text = " · ".join(x for x in [_pedido, _cliente, f"{n_docs} doc(s)", _estado_principal] if x)

    # ── Aviso de plazo: solo si hay algún documento NO aprobado ──
    # Si todos están "Aprobado", no procede plazo de respuesta (no hay nada que
    # corregir). Basta con un único documento distinto de Aprobado para mostrarlo.
    all_aprobado = bool(estado_counts) and all(
        str(e).strip().lower() == "aprobado" for e in estado_counts)
    deadline_block = "" if all_aprobado else f"""
      <!-- Aviso plazo -->
      <table cellpadding="0" cellspacing="0" style="width:100%;border-radius:8px;overflow:hidden;margin-bottom:28px;">
        <tr>
          <td style="background:#FFF8E1;border:1px solid #FFE082;border-radius:8px;padding:14px 18px;">
            <table cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td style="vertical-align:top;width:28px;font-size:18px;padding-top:1px;">&#9888;</td>
                <td>
                  <p style="margin:0;font-size:13px;font-weight:700;color:#BF6C00;">
                    Plazo de respuesta:
                    <span style="color:#C62828;">{deadline_str}</span>
                  </p>
                  <p style="margin:4px 0 0;font-size:12px;color:#795548;">
                    La documentación debe ser revisada, actualizada en ERP y subida antes de esta fecha.
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#EEF2F9;font-family:Arial,Helvetica,sans-serif;">

<!-- Preheader oculto: visible en la línea de preview de Outlook -->
<div style="display:none;max-height:0;overflow:hidden;font-size:1px;color:#EEF2F9;">{preheader_text}</div>

<table width="100%" cellpadding="0" cellspacing="0" style="background:#EEF2F9;padding:32px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="background:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(30,45,125,0.12);">

  <!-- ═══ HEADER ═══ -->
  <tr>
    <td style="background:{NAVY};padding:14px 28px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="vertical-align:middle;">{logo_html}</td>
          <td style="vertical-align:middle;text-align:right;">
            <p style="margin:0;font-size:14px;font-weight:700;color:#FFFFFF;letter-spacing:0.02em;">
              Devolución de Documentación
            </p>
            <p style="margin:4px 0 0;font-size:11px;color:{CYAN};letter-spacing:0.04em;text-transform:uppercase;">
              Notificación Automática
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- ═══ CUERPO ═══ -->
  <tr>
    <td style="padding:20px 28px 0;">

      <!-- Info del pedido -->
      <p style="margin:0 0 10px;font-size:10px;font-weight:700;color:{CYAN};text-transform:uppercase;letter-spacing:0.08em;">
        Datos del pedido
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;table-layout:fixed;">
        {info_rows_html}
      </table>

      <!-- Resumen estados -->
      <p style="margin:0 0 10px;font-size:10px;font-weight:700;color:{CYAN};text-transform:uppercase;letter-spacing:0.08em;">
        Resumen
      </p>
      <div style="margin-bottom:24px;">{summary_badges}</div>

      <!-- Tabla documentos -->
      <p style="margin:0 0 10px;font-size:10px;font-weight:700;color:{CYAN};text-transform:uppercase;letter-spacing:0.08em;">
        {doc_label} ({n_docs})
      </p>
      <table cellpadding="0" cellspacing="0" style="width:100%;border-radius:8px;overflow:hidden;border:1px solid #DDE3F5;margin-bottom:28px;">
        <thead><tr>{header_cells}</tr></thead>
        <tbody>{doc_rows}</tbody>
      </table>

      {deadline_block}

    </td>
  </tr>

  <!-- ═══ FOOTER ═══ -->
  <tr>
    <td style="background:#F4F7FC;border-top:3px solid {CYAN};padding:18px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td>
            <p style="margin:0;font-size:12px;font-weight:700;color:{NAVY};">
              Document Control
            </p>
            <p style="margin:3px 0 0;font-size:11px;color:#90A4AE;">
              DocFlow &nbsp;·&nbsp; © 2026 jparedesDS &nbsp;·&nbsp; Todos los derechos reservados
            </p>
          </td>
          <td style="text-align:right;vertical-align:middle;">
            <p style="margin:0;font-size:10px;color:#B0BEC5;">
              {datetime.now().strftime("%d/%m/%Y")}
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>

</table>
</td></tr>
</table>

</body>
</html>"""
    return html


def _data_erp_path() -> str:
    """Ruta efectiva del data_erp.xlsx (respeta el vínculo configurado).

    Antes importaba `utils.config` (módulo del DocFlow grande, inexistente en
    lite) y reventaba. Ahora resuelve la ruta vía data_source con fallback a la
    ruta por defecto de core.config.
    """
    try:
        from core import data_source
        return data_source.get_effective_path("data_erp")
    except Exception:
        try:
            from core.config import DATA_ERP_PATH
            return DATA_ERP_PATH
        except Exception:
            return ""


def lookup_erp(numero_pedido: str) -> dict:
    """Busca en data_erp.xlsx por Nº Pedido y devuelve Cliente, Material, etc."""
    import os
    path = _data_erp_path()
    if not numero_pedido or not path or not os.path.exists(path):
        return {}
    try:
        df = pd.read_excel(path, engine="openpyxl")
    except Exception:
        return {}

    mask = df["Nº Pedido"].astype(str).str.strip().str.contains(
        re.escape(numero_pedido), case=False, na=False
    )
    if mask.any():
        row = df[mask].iloc[0]
        return {k: str(row[k]) if pd.notna(row.get(k)) else ""
                for k in ("Cliente", "Material", "Nº PO")}
    return {}


def lookup_erp_by_npo(npo: str) -> dict:
    """Busca en data_erp.xlsx por Nº PO y devuelve Nº Pedido, Cliente, Material."""
    import os
    path = _data_erp_path()
    if not npo or not path or not os.path.exists(path):
        return {}
    try:
        df = pd.read_excel(path, engine="openpyxl")
    except Exception:
        return {}

    if "Nº PO" not in df.columns:
        return {}

    mask = df["Nº PO"].astype(str).str.strip().str.contains(
        re.escape(npo), case=False, na=False
    )
    if mask.any():
        row = df[mask].iloc[0]
        return {k: str(row[k]) if pd.notna(row.get(k)) else ""
                for k in ("Nº Pedido", "Cliente", "Material")}
    return {}


# ═══════════════════════════════════════════════════════
#  RED DE SEGURIDAD: resolver por Nº Doc. Cliente contra el ERP
#  Común a TODOS los portales. Si un parser no consigue Nº Pedido / Cliente /
#  Material / PO / Doc. EIPSA, se emparejan los códigos de doc del email
#  (Doc. Cliente) con la columna Nº Doc. Cliente del ERP y se rellenan los
#  huecos. SOLO rellena celdas vacías; nunca pisa lo que el parser ya resolvió.
# ═══════════════════════════════════════════════════════

_BLANK_VALUES = {"", "nan", "none", "nat", "-"}


def norm_doc_code(code) -> str:
    """Normaliza un código de doc de cliente para comparar sin ruido: sin
    espacios (internos incluidos) y en mayúsculas. Mantiene los guiones."""
    return re.sub(r"\s+", "", str(code or "")).upper()


def _is_blank(value) -> bool:
    return str(value).strip().lower() in _BLANK_VALUES


def erp_client_code_index() -> dict:
    """Índice {Nº Doc. Cliente normalizado → fila del ERP} sobre todo el
    monitoring. Import perezoso para evitar ciclos parsers↔services."""
    from core.services import monitoring
    idx: dict = {}
    for d in monitoring.get_monitoring_data():
        key = norm_doc_code(d.get("Nº Doc. Cliente"))
        if key and key not in idx:
            idx[key] = d
    return idx


def erp_header_from_row(row: dict) -> dict:
    """Extrae Nº Pedido / Supp. / Cliente / Material / PO de una fila del ERP.

    Separa el sufijo de suministro (-S00) del Nº Pedido.
    """
    out = {"n_pedido": "", "supp": "S00", "cliente": "", "material": "", "po": ""}
    ped = str(row.get("Nº Pedido", "")).strip()
    m = re.search(r"-(S\d{2})$", ped)
    if m:
        out["n_pedido"], out["supp"] = ped[:m.start()], m.group(1)
    else:
        out["n_pedido"] = ped
    out["cliente"] = str(row.get("Cliente", "") or "")
    out["material"] = str(row.get("Material", "") or "")
    out["po"] = str(row.get("Nº PO", "") or "").strip()
    return out


def enrich_missing_from_erp(df):
    """Red de seguridad para cualquier portal. Empareja cada 'Doc. Cliente' del
    email con su fila del ERP (por Nº Doc. Cliente) y rellena los huecos de
    Nº Pedido / Cliente / Material / PO / Supp. / Doc. EIPSA / Responsable.

    No hace nada si no hay columna 'Doc. Cliente' o si ningún código casa.
    Sólo rellena celdas vacías: si el parser ya resolvió un campo, se respeta.
    """
    if df is None or getattr(df, "empty", True) or "Doc. Cliente" not in df.columns:
        return df

    idx = erp_client_code_index()
    if not idx:
        return df

    matched = [idx.get(norm_doc_code(c)) for c in df["Doc. Cliente"]]
    if not any(m is not None for m in matched):
        return df

    # Cabecera del pedido: de la primera fila emparejada (todos los docs de una
    # devolución pertenecen al mismo pedido).
    hit = next((m for m in matched if m is not None), None)
    if hit is not None:
        header = erp_header_from_row(hit)
        for col, val in (
            ("Nº Pedido", header["n_pedido"]),
            ("Cliente", header["cliente"]),
            ("Material", header["material"]),
            ("PO", header["po"]),
            ("Supp.", header["supp"]),
        ):
            if val and col in df.columns:
                df[col] = [val if _is_blank(cur) else cur for cur in df[col]]

    # Doc. EIPSA: por fila, de su propia coincidencia exacta.
    if "Doc. EIPSA" in df.columns:
        df["Doc. EIPSA"] = [
            (str(m.get("Nº Doc. EIPSA", "") or "") or cur)
            if (_is_blank(cur) and m is not None) else cur
            for cur, m in zip(df["Doc. EIPSA"], matched)
        ]

    # Responsable: si quedó vacío y ya conocemos el Nº Pedido.
    if "Responsable" in df.columns and "Nº Pedido" in df.columns:
        df["Responsable"] = [
            get_responsable_initials(ped) if (_is_blank(resp) and not _is_blank(ped)) else resp
            for resp, ped in zip(df["Responsable"], df["Nº Pedido"])
        ]

    return df


FINAL_COLUMNS = [
    "Nº Pedido", "Supp.", "Responsable", "Cliente", "Material", "PO",
    "Doc. EIPSA", "Doc. Cliente", "Título", "Rev.", "Estado",
    "Tipo de documento", "Crítico", "Nº Transmittal", "Fecha",
]
