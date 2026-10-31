"""The Practice form: every kind of kit field, saving nothing (U0.10a Q4 a))."""

from django import forms
from django.utils.translation import gettext_lazy as _

from cucumber.core.kit import ListChoiceField, PickedDateField
from cucumber.references.lists import ListName


class PracticeForm(forms.Form):
    """Stage, medium, container and date, as Phase 1's forms will have them."""

    stage = ListChoiceField(ListName.STAGES, label=_("Stage"))
    medium = ListChoiceField(ListName.MEDIA_CODES, label=_("Medium"))
    container = ListChoiceField(ListName.CONTAINER_TYPES, label=_("Container"))
    date = PickedDateField(label=_("Date"))
