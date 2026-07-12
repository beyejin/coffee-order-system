package com.example.coffee.order;

import java.lang.System.Logger;
import java.lang.System.Logger.Level;

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
