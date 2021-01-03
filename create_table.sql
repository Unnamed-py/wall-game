CREATE TABLE "User"
(
	symbol varchar(5) not null,
	name varchar(25) not null
		constraint User_pk
			primary key,
	password varchar(75) not null
)