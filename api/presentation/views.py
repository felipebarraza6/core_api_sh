import os
import re
import html
import markdown
from django.conf import settings
from django.views.generic import TemplateView

class PresentationView(TemplateView):
    template_name = "presentation/landing.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site_title"] = "SmartHydro Architect"
        context["page_title"] = "Technical Ecosystem"
        
        # Load AGENTS.md content
        agents_path = os.path.join(settings.BASE_DIR, 'api', 'presentation', 'AGENTS.md')
        try:
            with open(agents_path, 'r') as f:
                md_content = f.read()
            # Convert to HTML
            html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
            context["agents_doc"] = self._process_mermaid(html_content)
        except Exception as e:
            context["agents_doc"] = f"<p>Error loading documentation: {str(e)}</p>"

        # Load API_ARCHITECTURE.md content
        arch_path = os.path.join(settings.BASE_DIR, 'api', 'presentation', 'API_ARCHITECTURE.md')
        try:
            with open(arch_path, 'r') as f:
                arch_content = f.read()
            # Convert to HTML
            arch_html = markdown.markdown(arch_content, extensions=['fenced_code'])
            context["architecture_doc"] = self._process_mermaid(arch_html)
        except Exception as e:
            context["architecture_doc"] = f"<p>Error loading architecture: {str(e)}</p>"
            
        # Load TRACEABILITY_DIAGRAM.md content
        trace_path = os.path.join(settings.BASE_DIR, 'api', 'presentation', 'TRACEABILITY_DIAGRAM.md')
        try:
            with open(trace_path, 'r') as f:
                trace_content = f.read()
            # Convert to HTML
            trace_html = markdown.markdown(trace_content, extensions=['fenced_code', 'tables'])
            context["traceability_doc"] = self._process_mermaid(trace_html)
        except Exception as e:
            context["traceability_doc"] = f"<p>Error loading traceability: {str(e)}</p>"

        return context

    def _process_mermaid(self, html_content):
        """
        Convert standard markdown code blocks to mermaid-js compatible divs.
        Pattern: <pre><code class="language-mermaid">CONTENT</code></pre>
        Target: <div class="mermaid">CONTENT (unescaped)</div>
        """
        pattern = r'<pre><code class="language-mermaid">(.*?)</code></pre>'
        
        def replacer(match):
            # Unescape HTML entities (e.g. &gt; to >) so mermaid can parse arrows
            content = html.unescape(match.group(1))
            return f'<div class="mermaid">{content}</div>'
            
        return re.sub(pattern, replacer, html_content, flags=re.DOTALL)
