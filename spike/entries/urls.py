from django.urls import path, re_path

from . import views

app_name = "entries"

# Only the two kits being compared are valid; anything else is a 404.
KIT = r"(?P<kit>daisy|basecoat)"

urlpatterns = [
    path("", views.home, name="home"),
    re_path(rf"^{KIT}/$", views.entry_page, name="page"),
    re_path(rf"^{KIT}/entries/$", views.create_entry, name="create"),
    re_path(rf"^{KIT}/login/$", views.kit_login, name="login"),
    re_path(rf"^{KIT}/logout/$", views.kit_logout, name="logout"),
]
