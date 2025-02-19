from django.db import models
from django.contrib.auth.models import User
from django.utils.timezone import now

# Definimos los roles de usuario
ROLES = (
    ('admin', 'Administrador'),
    ('empleado', 'Empleado de Sucursal'),
    ('cliente', 'Cliente'),
)

class Perfil(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    rol = models.CharField(max_length=10, choices=ROLES, default='cliente')
    sucursal = models.ForeignKey('Sucursal', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.rol}"

class Sucursal(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200)

    def __str__(self):
        return self.nombre

class Medicamento(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.nombre


class Inventario(models.Model):
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE)
    medicamento = models.ForeignKey(Medicamento, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.medicamento.nombre} en {self.sucursal.nombre}: {self.cantidad} unidades"

    def tiene_stock_suficiente(self, cantidad_requerida):
        """ Verifica si hay suficiente stock disponible """
        return self.cantidad >= cantidad_requerida

    def ajustar_stock(self, cantidad):
        """
        Ajusta el stock asegurando que no haya valores negativos.
        - `cantidad` → Puede ser positiva o negativa.
        """
        self.cantidad = max(0, self.cantidad + cantidad)
        self.save()

    def transferir_stock(self, inventario_destino, cantidad):
        """
        Transfiere stock entre sucursales de manera más eficiente.
        - `inventario_destino` → Instancia de `Inventario` en la sucursal destino.
        - `cantidad` → Cantidad de medicamento a transferir.
        """
        if self.tiene_stock_suficiente(cantidad):
            self.ajustar_stock(-cantidad)  # Reduce stock en la sucursal de origen
            inventario_destino.ajustar_stock(cantidad)  # Aumenta stock en la sucursal destino
            return True
        return False

    def aumentar_stock(self, cantidad, usuario):
        """
        Aumenta el stock del medicamento en la sucursal.
        - `cantidad`: Número de unidades a agregar.
        - `usuario`: Empleado que realizó la acción (para registro en historial).
        """
        if cantidad > 0:
            self.cantidad += cantidad
            self.save()

            # ✅ Registrar en el historial de ajustes de stock
            HistorialStock.objects.create(
                inventario=self,
                cantidad_aumentada=cantidad,
                empleado=usuario
            )

            return True
        return False


class HistorialStock(models.Model):
    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE)  # Ya está en la BD
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, default=1)  # ✅ Agregamos relación
    cantidad_aumentada = models.PositiveIntegerField()
    fecha = models.DateTimeField(auto_now_add=True)
    empleado = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Historial {self.id}: +{self.cantidad_aumentada} en {self.sucursal.nombre} el {self.fecha}"


class Pedido(models.Model):
    OPCIONES_ENTREGA = [
        ('retiro_sucursal', 'Retirar en Sucursal'),
        ('envio_origen', 'Enviar a la Sucursal de Origen'),
    ]

    cliente = models.ForeignKey(User, on_delete=models.CASCADE)
    medicamento = models.ForeignKey(Medicamento, on_delete=models.CASCADE)
    sucursal_solicitada = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name="pedidos_solicitados")
    sucursal_envio = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name="pedidos_enviados", null=True,
                                       blank=True)
    cantidad = models.PositiveIntegerField()
    estado = models.CharField(max_length=20, choices=[('pendiente', 'Pendiente'), ('completado', 'Completado'),
                                                      ('cancelado', 'Cancelado')], default='pendiente')
    fecha_pedido = models.DateTimeField(default=now, editable=False)
    opcion_entrega = models.CharField(max_length=20, choices=OPCIONES_ENTREGA, default='retiro_sucursal')

    def __str__(self):
        return f"Pedido {self.id} - {self.medicamento.nombre} ({self.cantidad} unidades) - {self.estado}"

    def marcar_completado(self):
        """ Marca el pedido como completado si se ha recibido el stock necesario. """
        if self.estado == 'pendiente':
            self.estado = 'completado'
            self.save()

    def cancelar_pedido(self):
        """ Cancela el pedido y regresa el stock a la sucursal si aplica. """
        if self.estado == 'pendiente':
            inventario = Inventario.objects.filter(medicamento=self.medicamento,
                                                   sucursal=self.sucursal_solicitada).first()
            if inventario:
                inventario.ajustar_stock(self.cantidad)
            self.estado = 'cancelado'
            self.save()

class Transferencia(models.Model):
    medicamento = models.ForeignKey(Medicamento, on_delete=models.CASCADE)
    sucursal_origen = models.ForeignKey(Sucursal, related_name='origen', on_delete=models.CASCADE)
    sucursal_destino = models.ForeignKey(Sucursal, related_name='destino', on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField()
    fecha = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(
        max_length=20,
        choices=[
            ('pendiente', 'Pendiente'),
            ('aprobada', 'Aprobada'),
            ('rechazada', 'Rechazada')
        ],
        default='pendiente'
    )
    pedido_relacionado = models.ForeignKey(
        Pedido, on_delete=models.SET_NULL, null=True, blank=True, related_name="transferencias"
    )  # ✅ Relación con el pedido

    def __str__(self):
        return f"Transferencia de {self.cantidad} {self.medicamento} de {self.sucursal_origen} a {self.sucursal_destino} - {self.estado}"

    def aprobar_transferencia(self):
        """ Aprueba la transferencia y actualiza el stock en ambas sucursales. """
        if self.estado == 'pendiente':
            inventario_origen = Inventario.objects.filter(
                medicamento=self.medicamento,
                sucursal=self.sucursal_origen
            ).first()
            inventario_destino, created = Inventario.objects.get_or_create(
                medicamento=self.medicamento,
                sucursal=self.sucursal_destino,
                defaults={'cantidad': 0}
            )

            if inventario_origen and inventario_origen.transferir_stock(inventario_destino, self.cantidad):
                self.estado = 'aprobada'
                self.save()

                # ✅ Si hay un pedido relacionado, actualizar su estado
                if self.pedido_relacionado:
                    self.pedido_relacionado.marcar_completado()

                    # ✅ Restar stock de la sucursal destino al completar el pedido
                    inventario_cliente = Inventario.objects.filter(
                        medicamento=self.pedido_relacionado.medicamento,
                        sucursal=self.pedido_relacionado.sucursal_solicitada
                    ).first()

                    if inventario_cliente and inventario_cliente.tiene_stock_suficiente(
                            self.pedido_relacionado.cantidad):
                        inventario_cliente.ajustar_stock(-self.pedido_relacionado.cantidad)

    def rechazar_transferencia(self):
        """ Rechaza la transferencia y cancela el pedido asociado si aplica. """
        if self.estado == 'pendiente':
            self.estado = 'rechazada'
            self.save()

            if self.pedido_relacionado:
                self.pedido_relacionado.cancelar_pedido()