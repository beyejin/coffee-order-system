package com.example.coffee;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.mysql.MySQLContainer;

@SpringBootTest
@Import(TestcontainersConfiguration.class)
class MigrationUpgradeTest {

	private static final String UPGRADE_DATABASE = "coffee_upgrade";
	private static final String ROOT_USERNAME = "root";

	@Autowired
	private MySQLContainer mysqlContainer;

	@Test
	void V1_V5_스키마와_데이터를_V6로_업그레이드한다() {
		JdbcTemplate adminJdbcTemplate = jdbcTemplate(mysqlContainer.getJdbcUrl(), ROOT_USERNAME);
		adminJdbcTemplate.execute("DROP DATABASE IF EXISTS " + UPGRADE_DATABASE);
		adminJdbcTemplate.execute("CREATE DATABASE " + UPGRADE_DATABASE);
		adminJdbcTemplate.execute("GRANT ALL PRIVILEGES ON " + UPGRADE_DATABASE + ".* TO '"
				+ mysqlContainer.getUsername() + "'@'%'");

		try {
			String upgradeUrl = "jdbc:mysql://%s:%d/%s?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true"
					.formatted(mysqlContainer.getHost(), mysqlContainer.getMappedPort(3306), UPGRADE_DATABASE);

			Flyway.configure()
					.dataSource(upgradeUrl, mysqlContainer.getUsername(), mysqlContainer.getPassword())
					.target("5")
					.load()
					.migrate();

			JdbcTemplate upgradeJdbcTemplate = jdbcTemplate(upgradeUrl, mysqlContainer.getUsername());
			upgradeJdbcTemplate.update("UPDATE `user` SET balance = 10000 WHERE id = 1");
			upgradeJdbcTemplate.update("""
					INSERT INTO point_history (user_id, amount, type)
					VALUES (1, 10000, 'CHARGE')
					""");

			Flyway.configure()
					.dataSource(upgradeUrl, mysqlContainer.getUsername(), mysqlContainer.getPassword())
					.load()
					.migrate();

			assertEquals(10000L, upgradeJdbcTemplate.queryForObject(
					"SELECT balance FROM users WHERE id = 1", Long.class));
			assertEquals(1, upgradeJdbcTemplate.queryForObject(
					"SELECT COUNT(*) FROM point_history WHERE user_id = 1", Integer.class));
			assertEquals(3, upgradeJdbcTemplate.queryForObject(
					"SELECT COUNT(*) FROM menus", Integer.class));
			assertEquals(6, createdAtPrecision(upgradeJdbcTemplate, "users"));
			assertEquals(6, createdAtPrecision(upgradeJdbcTemplate, "point_history"));
		} finally {
			adminJdbcTemplate.execute("DROP DATABASE IF EXISTS " + UPGRADE_DATABASE);
		}
	}

	private JdbcTemplate jdbcTemplate(String url, String username) {
		return new JdbcTemplate(new DriverManagerDataSource(
				url,
				username,
				mysqlContainer.getPassword()
		));
	}

	private int createdAtPrecision(JdbcTemplate jdbcTemplate, String tableName) {
		return jdbcTemplate.queryForObject("""
				SELECT datetime_precision
				FROM information_schema.columns
				WHERE table_schema = DATABASE()
				  AND table_name = ?
				  AND column_name = 'created_at'
				""", Integer.class, tableName);
	}
}
