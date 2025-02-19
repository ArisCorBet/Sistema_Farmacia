from django.contrib import admin
from .models import Perfil, Sucursal, Medicamento, Inventario, Pedido, Transferencia

from .models import HistorialStock

class HistorialStockAdmin(admin.ModelAdmin):
    list_display = ('inventario', 'empleado', 'cantidad_aumentada', 'fecha')
    list_filter = ('empleado', 'fecha')
    search_fields = ('inventario__medicamento__nombre', 'empleado__username')

admin.site.register(HistorialStock, HistorialStockAdmin)


class PerfilAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'email', 'rol', 'sucursal', 'fecha_registro')
    list_filter = ('rol', 'sucursal', 'usuario__date_joined')
    search_fields = ('usuario__username', 'usuario__email', 'rol')
    list_editable = ('sucursal', 'rol')

    def email(self, obj):
        """Muestra el correo electrónico del usuario."""
        return obj.usuario.email

    email.admin_order_field = 'usuario__email'
    email.short_description = 'Correo Electrónico'

    def fecha_registro(self, obj):
        """Muestra la fecha de registro del usuario."""
        return obj.usuario.date_joined.strftime('%Y-%m-%d %H:%M')

    fecha_registro.admin_order_field = 'usuario__date_joined'
    fecha_registro.short_description = 'Fecha de Registro'


class InventarioInline(admin.TabularInline):
    model = Inventario
    extra = 1

class SucursalAdmin(admin.ModelAdmin):
    inlines = [InventarioInline]

class InventarioAdmin(admin.ModelAdmin):
    list_display = ('medicamento', 'sucursal', 'cantidad')
    list_filter = ('sucursal', 'medicamento')
    search_fields = ('medicamento__nombre', 'sucursal__nombre')
    list_editable = ('cantidad',)

    def ajustar_stock(self, request, queryset):
        for inventario in queryset:
            inventario.cantidad = max(inventario.cantidad, 0)  # Asegurar que no sea negativo
            inventario.save()
        self.message_user(request, "Stock ajustado correctamente.")

    ajustar_stock.short_description = "Ajustar stock (evitar valores negativos)"


class PedidoAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'medicamento', 'sucursal_solicitada', 'cantidad', 'estado', 'opcion_entrega', 'fecha_pedido')
    list_filter = ('estado', 'sucursal_solicitada', 'opcion_entrega', 'fecha_pedido')
    search_fields = ('cliente__username', 'medicamento__nombre')
    ordering = ('-fecha_pedido',)
    list_editable = ('estado',)
    actions = ['marcar_completado', 'cancelar_pedido']

    def marcar_completado(self, request, queryset):
        queryset.update(estado='completado')
        self.message_user(request, "Los pedidos seleccionados han sido marcados como completados.")

    def cancelar_pedido(self, request, queryset):
        queryset.update(estado='cancelado')
        self.message_user(request, "Los pedidos seleccionados han sido cancelados.")

    marcar_completado.short_description = "Marcar pedidos como completados"
    cancelar_pedido.short_description = "Cancelar pedidos seleccionados"


class TransferenciaAdmin(admin.ModelAdmin):
    list_display = ('medicamento', 'sucursal_origen', 'sucursal_destino', 'cantidad', 'estado', 'pedido_relacionado', 'fecha')
    list_filter = ('estado', 'sucursal_origen', 'sucursal_destino', 'fecha')
    search_fields = ('medicamento__nombre', 'sucursal_origen__nombre', 'sucursal_destino__nombre', 'pedido_relacionado__id')
    list_editable = ('estado',)
    actions = ['aprobar_transferencia', 'rechazar_transferencia', 'crear_transferencia_manual']

    def aprobar_transferencia(self, request, queryset):
        """Aprueba transferencias pendientes y actualiza pedidos relacionados."""
        for transferencia in queryset:
            if transferencia.estado == 'pendiente':
                inventario_origen = Inventario.objects.filter(
                    medicamento=transferencia.medicamento,
                    sucursal=transferencia.sucursal_origen
                ).first()
                inventario_destino, created = Inventario.objects.get_or_create(
                    medicamento=transferencia.medicamento,
                    sucursal=transferencia.sucursal_destino,
                    defaults={'cantidad': 0}
                )

                if inventario_origen and inventario_origen.transferir_stock(inventario_destino, transferencia.cantidad):
                    transferencia.estado = 'aprobada'
                    transferencia.save()

                    # ✅ Si hay un pedido asociado, actualizar su estado
                    pedido = transferencia.pedido_relacionado
                    if pedido and pedido.estado == 'pendiente':
                        pedido.estado = 'completado'
                        pedido.save()

                    self.message_user(request, f'Transferencia aprobada y stock actualizado.')
                else:
                    self.message_user(request, 'No hay suficiente stock en la sucursal de origen.', level='error')

    def rechazar_transferencia(self, request, queryset):
        """Rechaza transferencias y cancela pedidos asociados."""
        for transferencia in queryset:
            transferencia.estado = 'rechazada'
            transferencia.save()

            pedido = transferencia.pedido_relacionado
            if pedido and pedido.estado == 'pendiente':
                pedido.estado = 'cancelado'
                pedido.save()

        self.message_user(request, "Transferencia(s) rechazadas y pedidos cancelados.")

    def crear_transferencia_manual(self, request, queryset):
        """Permite al administrador crear transferencias manualmente entre sucursales."""
        for inventario in queryset:
            if inventario.cantidad > 0:
                sucursales_destino = Sucursal.objects.exclude(id=inventario.sucursal.id)
                if sucursales_destino.exists():
                    sucursal_destino = sucursales_destino.first()
                    cantidad_transferir = min(inventario.cantidad, 10)  # ✅ Se mantiene el límite

                    transferencia = Transferencia.objects.create(
                        medicamento=inventario.medicamento,
                        sucursal_origen=inventario.sucursal,
                        sucursal_destino=sucursal_destino,
                        cantidad=cantidad_transferir,
                        estado="pendiente"
                    )
                    self.message_user(request, f'Transferencia creada de {transferencia.cantidad} unidades.')

    aprobar_transferencia.short_description = "Aprobar Transferencias y Completar Pedidos"
    rechazar_transferencia.short_description = "Rechazar Transferencias"
    crear_transferencia_manual.short_description = "Crear Transferencia Manual desde Inventario"


admin.site.register(Perfil, PerfilAdmin)
admin.site.register(Sucursal, SucursalAdmin)
admin.site.register(Medicamento)
admin.site.register(Inventario, InventarioAdmin)
admin.site.register(Pedido, PedidoAdmin)
admin.site.register(Transferencia, TransferenciaAdmin)
