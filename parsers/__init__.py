from . import bradesco_pdf
from . import caixa_pdf

# Registry of available parsers
AVAILABLE_PARSERS = {
    "Bradesco (PDF)": bradesco_pdf,
    "Caixa Econômica (PDF)": caixa_pdf
}

def get_parser(name):
    return AVAILABLE_PARSERS.get(name)
