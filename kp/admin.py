from django.contrib import admin

from .models import KP, KPEquipment, KPItem


@admin.register(KPEquipment)
class KPEquipmentAdmin(admin.ModelAdmin):
    """Справочник заполняется ночным импортом — здесь он только для просмотра."""

    list_display = ("name", "group", "price", "weight", "space", "volume", "length", "is_active", "updated_at")
    list_filter = ("is_active", "group")
    search_fields = ("name",)
    readonly_fields = ("name", "group", "price", "weight", "space", "volume", "length", "is_active", "updated_at")

    def has_add_permission(self, request):
        return False


class KPItemInline(admin.TabularInline):
    """Позиции — снимок на момент сборки, править их задним числом нельзя."""

    model = KPItem
    extra = 0
    readonly_fields = ("equipment", "name", "price", "weight", "space", "volume", "quantity")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(KP)
class KPAdmin(admin.ModelAdmin):
    list_display = ("sequence_number", "shortname", "landlord", "rent_day", "date_created")
    list_filter = ("landlord", "date_created")
    search_fields = ("sequence_number", "shortname", "address")
    readonly_fields = ("sequence_number", "date_created", "author_user_id")
    inlines = [KPItemInline]
