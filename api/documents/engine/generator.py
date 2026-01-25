
import os
import shutil
import datetime
from django.conf import settings
from django.core.files import File

# Try imports
try:
    from docxtpl import DocxTemplate
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import openpyxl
    HAS_XLSX = True
except ImportError:
    HAS_XLSX = False

class DocumentGenerator:
    """
    Motor de generación de documentos.
    Combina un Template (Word/Excel) con un Contexto (Dict) para producir un archivo final.
    """
    
    def __init__(self, template_obj):
        self.template = template_obj
        self.output_dir = os.path.join(settings.MEDIA_ROOT, 'generated_docs')
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, context_data, output_name=None):
        """
        Ejecuta la generación.
        :param context_data: Diccionario con variables {client_name: 'Foo', ...}
        :param output_name: Nombre opcional del archivo (sin extensión)
        :return: Path del archivo generado
        """
        if not output_name:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"{self.template.code}_{ts}"
            
        ext = 'docx' if self.template.engine_type == 'docx' else 'xlsx'
        filename = f"{output_name}.{ext}"
        output_path = os.path.join(self.output_dir, filename)
        
        # Copiar template a path temporal seguro para procesar
        # (Ojo: docxtpl necesita path fisico o file-like)
        template_path = self.template.file.path
        
        if self.template.engine_type == 'docx':
            return self._generate_docx(template_path, context_data, output_path)
        elif self.template.engine_type == 'xlsx':
            return self._generate_xlsx(template_path, context_data, output_path)
        elif self.template.engine_type == 'pdf':
            return self._generate_pdf(context_data, output_path)
        else:
            raise ValueError(f"Engine no soportado: {self.template.engine_type}")

    def render_html(self, context):
        """Renderiza el HTML en memoria sin guardar archivo."""
        from django.template import Template, Context
        
        # 1. Obtener HTML crudo
        raw_html = ""
        if self.template.html_content:
            raw_html = self.template.html_content
        elif self.template.file:
            with open(self.template.file.path, 'r') as f:
                raw_html = f.read()
        else:
            return "<h1>Error: No hay contenido HTML definido</h1>"

        # 2. Renderizar con Django Engine
        django_template = Template(raw_html)
        return django_template.render(Context(context))

    def _generate_pdf(self, context, output_path):
        rendered_html = self.render_html(context)
        
        # 3. Guardar (Simulando PDF)
        real_output_path = output_path.replace('.pdf', '.html')
        with open(real_output_path, 'w') as f:
            f.write(rendered_html)
            
        return real_output_path


    def _generate_docx(self, input_path, context, output_path):
        if not HAS_DOCX:
            # Fallback for testing/audit without libraries
            shutil.copy(input_path, output_path)
            return output_path
            
        doc = DocxTemplate(input_path)
        doc.render(context)
        doc.save(output_path)
        return output_path

    def _generate_xlsx(self, input_path, context, output_path):
        if not HAS_XLSX:
            shutil.copy(input_path, output_path)
            return output_path
            
        # Basic replacement in Excel cells {{key}} -> value
        # Limite: Solo scannea primeras 100 filas/columnas para performance
        wb = openpyxl.load_workbook(input_path)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(min_row=1, max_row=100, min_col=1, max_col=20):
                for cell in row:
                    if cell.value and isinstance(cell.value, str) and "{{" in cell.value:
                        # Simple replacement
                        for k, v in context.items():
                            token = f"{{{{{k}}}}}"
                            if token in cell.value:
                                cell.value = cell.value.replace(token, str(v))
        
        wb.save(output_path)
        return output_path
