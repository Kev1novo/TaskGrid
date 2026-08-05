from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        USER = "user", "普通用户"

    role = models.CharField(
        "角色",
        max_length=20,
        choices=Role.choices,
        default=Role.USER,
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "users"
        verbose_name = "用户"
        verbose_name_plural = "用户"

    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser
