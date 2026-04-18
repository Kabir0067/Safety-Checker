from django.db import models


class BotUser(models.Model):
    id = models.AutoField(primary_key=True)
    telegram_id = models.CharField(max_length=50, unique=True)
    username = models.CharField(max_length=100, null=True, blank=True)
    language = models.CharField(max_length=10, default="en")
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "users"
        verbose_name = "Пользователь бота"
        verbose_name_plural = "Пользователи бота"

    def __str__(self) -> str:
        return f"{self.telegram_id} ({self.username or 'no_username'})"


class Company(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    company_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    registered_address = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50, default="unknown")
    score = models.IntegerField(default=0)
    website_domain = models.CharField(max_length=255, null=True, blank=True)
    contact_email = models.CharField(max_length=255, null=True, blank=True)
    phone_number = models.CharField(max_length=50, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    jurisdiction = models.CharField(max_length=100, null=True, blank=True)
    last_updated = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "companies"
        verbose_name = "Компания"
        verbose_name_plural = "Компании"

    def __str__(self) -> str:
        number = f" [{self.company_number}]" if self.company_number else ""
        return f"{self.name}{number}"


class UserCheck(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        BotUser,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="checks",
        null=True,
        blank=True,
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        db_column="company_id",
        related_name="checks",
        null=True,
        blank=True,
    )
    contract_number = models.CharField(max_length=100, null=True, blank=True)
    contract_date = models.DateField(null=True, blank=True)
    extracted_company_name = models.CharField(max_length=255, null=True, blank=True)
    extracted_company_number = models.CharField(max_length=50, null=True, blank=True)
    extracted_address = models.TextField(null=True, blank=True)
    website_domain = models.CharField(max_length=255, null=True, blank=True)
    total_score = models.IntegerField(default=0)
    safety_rating = models.CharField(max_length=10, default="unknown")
    detailed_scores = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "user_checks"
        verbose_name = "Проверка"
        verbose_name_plural = "Проверки"

    def __str__(self) -> str:
        return f"Check #{self.id} ({self.safety_rating}, {self.total_score})"


class SuspiciousCompany(models.Model):
    id = models.AutoField(primary_key=True)
    company_name = models.CharField(max_length=255)
    company_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    evidence = models.TextField(null=True, blank=True)
    source = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, default="active")
    website_domain = models.CharField(max_length=255, null=True, blank=True)
    registered_address = models.TextField(null=True, blank=True)
    contact_phone = models.CharField(max_length=50, null=True, blank=True)
    contact_email = models.CharField(max_length=255, null=True, blank=True)
    added_by = models.ForeignKey(
        BotUser,
        on_delete=models.SET_NULL,
        db_column="added_by",
        related_name="added_suspicious_companies",
        null=True,
        blank=True,
    )
    verified_by = models.ForeignKey(
        BotUser,
        on_delete=models.SET_NULL,
        db_column="verified_by",
        related_name="verified_suspicious_companies",
        null=True,
        blank=True,
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "suspicious_companies"
        verbose_name = "Подозрительная компания"
        verbose_name_plural = "Подозрительные компании"

    def __str__(self) -> str:
        return self.company_name
