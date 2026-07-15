package com.example.coffee.infra.redis;

import java.lang.System.Logger;
import java.lang.System.Logger.Level;

import com.example.coffee.domain.order.event.OrderPaidEvent;
import com.example.coffee.domain.ranking.repository.PopularMenuCounter;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class PopularMenuRedisEventListener {

	private static final Logger LOGGER = System.getLogger(PopularMenuRedisEventListener.class.getName());

	private final PopularMenuCounter popularMenuCounter;

	public PopularMenuRedisEventListener(PopularMenuCounter popularMenuCounter) {
		this.popularMenuCounter = popularMenuCounter;
	}

	@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
	public void recordAfterCommit(OrderPaidEvent event) {
		try {
			popularMenuCounter.record(event.orderId(), event.menuId(), event.orderedAt());
		} catch (RuntimeException exception) {
			LOGGER.log(Level.WARNING, "인기 메뉴 Redis read model 갱신 실패", exception);
		}
	}
}
