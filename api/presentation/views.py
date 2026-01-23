from django.views.generic import TemplateView

class PresentationView(TemplateView):
    template_name = "presentation/landing.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site_title"] = "SmartHydro Architect"
        context["page_title"] = "Technical Ecosystem"
        return context
