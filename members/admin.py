from django.contrib import admin

from members.models import Enrollment, Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('member_id', 'first_name', 'last_name', 'zip_code', 'subscriber_id')
    search_fields = ('member_id', 'last_name', 'subscriber_id')
    list_filter = ('relationship_to_subscriber',)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('member', 'product', 'effective_date', 'termination_date')
    list_filter = ('product__lob',)
    search_fields = ('member__member_id',)
    raw_id_fields = ('member', 'product')
