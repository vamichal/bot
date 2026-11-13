from django.contrib import admin

from .models import KPEquipment


@admin.register(KPEquipment)
class KPEquipmentAdmin(admin.ModelAdmin):
    """Справочник заполняется ночным импортом — здесь он только для просмотра."""

    list_display = ("name", "group", "price", "weight", "space", "volume", "length", "is_active", "updated_at")
    list_filter = ("is_active", "group")
    search_fields = ("name",)
    readonly_fields = ("name", "group", "price", "weight", "space", "volume", "length", "is_active", "updated_at")

    def has_add_permission(self, request):
        return False
