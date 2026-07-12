CREATE TABLE menu
(
    id    BIGINT AUTO_INCREMENT PRIMARY KEY,
    name  VARCHAR(50) NOT NULL,
    price BIGINT      NOT NULL
);

INSERT INTO menu (name, price)
VALUES ('아메리카노', 4500),
       ('카페라떼', 5000),
       ('카페모카', 5500);
