from django.contrib import admin
from .models import Participant, CustomUser

@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'nationality', 'paid')
    list_filter = ('paid', 'nationality')
    search_fields = ('full_name',)

admin.site.register(CustomUser)