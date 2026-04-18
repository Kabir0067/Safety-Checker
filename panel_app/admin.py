from django.contrib import admin

from .models import BotUser, Company, SuspiciousCompany, UserCheck

admin.site.site_header = "Панель администрирования Safety Checker"
admin.site.site_title = "Safety Checker Admin"
admin.site.index_title = "Управление системой и базой бота"


@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = ("id", "telegram_id", "username", "language", "created_at")
    search_fields = ("telegram_id", "username")
    list_filter = ("language",)
    ordering = ("-id",)
    readonly_fields = ("created_at",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "company_number",
        "status",
        "country",
        "jurisdiction",
        "score",
        "website_domain",
        "last_updated",
    )
    search_fields = ("name", "company_number", "website_domain", "country", "jurisdiction")
    list_filter = ("status", "country", "jurisdiction")
    ordering = ("-id",)
    readonly_fields = ("created_at", "last_updated")


@admin.register(UserCheck)
class UserCheckAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "company",
        "contract_number",
        "total_score",
        "safety_rating",
        "created_at",
    )
    search_fields = (
        "contract_number",
        "extracted_company_name",
        "extracted_company_number",
        "website_domain",
    )
    list_filter = ("safety_rating", "contract_date")
    ordering = ("-id",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(SuspiciousCompany)
class SuspiciousCompanyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "company_name",
        "company_number",
        "status",
        "source",
        "website_domain",
        "created_at",
    )
    search_fields = ("company_name", "company_number", "website_domain")
    list_filter = ("status", "source")
    ordering = ("-id",)
    readonly_fields = ("created_at", "updated_at", "verified_at")
