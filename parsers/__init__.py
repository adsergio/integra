from . import bradesco_pdf

# Registry of available parsers
AVAILABLE_PARSERS = {
    "Bradesco (PDF)": bradesco_pdf
}

def get_parser(name):
    return AVAILABLE_PARSERS.get(name)
