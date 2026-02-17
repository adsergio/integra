try:
    import zipfile
    import xml.etree.ElementTree as ET
    
    path = r"c:\Users\Sergio\Documents\Apps-Contabilidade\integra\Objetivo do sistema.docx"
    
    with zipfile.ZipFile(path) as z:
        xml_content = z.read('word/document.xml')
    
    tree = ET.fromstring(xml_content)
    
    # Define namespace map (Word uses namespaces)
    namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    
    text = []
    for node in tree.iter():
        if node.tag.endswith('}t'):  # Text node
            if node.text:
                text.append(node.text)
        elif node.tag.endswith('}p'): # Paragraph (add newline)
            text.append('\n')
            
    print("".join(text))

except Exception as e:
    print(f"Error reading docx: {e}")
