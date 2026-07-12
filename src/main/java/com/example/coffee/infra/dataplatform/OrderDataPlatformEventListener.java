package com.example.coffee.infra.dataplatform;

import java.lang.System.Logger;
import java.lang.System.Logger.Level;

import com.example.coffee.domain.order.event.OrderDataMessage;
import com.example.coffee.domain.order.event.OrderPaidEvent;
import com.example.coffee.domain.order.service.DataPlatformClient;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderDataPlatformEventListener {

	private static final Logger LOGGER = System.getLogger(OrderDataPlatformEventListener.class.getName());

	private final DataPlatformClient dataPlatformClient;

	public OrderDataPlatformEventListener(DataPlatformClient dataPlatformClient) {
		this.dataPlatformClient = dataPlatformClient;
	}

	@Async
	@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
	public void sendAfterCommit(OrderPaidEvent event) {
		try {
			dataPlatformClient.send(new OrderDataMessage(
					event.userId(),
					event.menuId(),
					event.paymentAmount()
			));
		} catch (RuntimeException exception) {
			LOGGER.log(Level.WARNING, "주문 데이터 전송 실패", exception);
		}
	}
}
