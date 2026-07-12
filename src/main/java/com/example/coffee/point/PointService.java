package com.example.coffee.point;

import com.example.coffee.common.BusinessException;
import com.example.coffee.common.ErrorCode;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PointService {

	private final UserRepository userRepository;
	private final PointHistoryRepository pointHistoryRepository;

	public PointService(UserRepository userRepository, PointHistoryRepository pointHistoryRepository) {
		this.userRepository = userRepository;
		this.pointHistoryRepository = pointHistoryRepository;
	}

	@Transactional
	public ChargePointResponse charge(Long userId, Long amount) {
		if (amount == null || amount <= 0) {
			throw new BusinessException(ErrorCode.INVALID_CHARGE_AMOUNT);
		}

		User user = userRepository.findByIdForUpdate(userId)
				.orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

		try {
			user.charge(amount);
		} catch (ArithmeticException exception) {
			throw new BusinessException(ErrorCode.POINT_BALANCE_OVERFLOW);
		}
		pointHistoryRepository.save(PointHistory.charge(user, amount));

		return new ChargePointResponse(user.getId(), user.getBalance());
	}
}
