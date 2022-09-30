# popug-task-tracker
A training project for Async Architecture course 2022

## HW 1

> Разобрать каждое требование на составляющие (актор, команда, событие, query). Определить, как все бизнес цепочки будут выглядеть и на какие шаги они будут разбиваться.

### Task tracker

> Таск-трекер должен быть отдельным дашбордом и доступен всем сотрудникам компании UberPopug Inc. 
> Каждый сотрудник должен иметь возможность видеть в отдельном месте список заассайненных на него задач

Actor: User
Command: List Tasks | List Tasks filtered by User
Data: User Role
Event: -

> Авторизация в таск-трекере должна выполняться через общий сервис авторизации UberPopug Inc (у нас там инновационная система авторизации на основе формы клюва).

Actor: User
Command: Log in a User 
Data: `beak_geometry`
Event: User.LoggedIn

> Новые таски может создавать кто угодно (администратор, начальник, разработчик, менеджер и любая другая роль).

Actor: User
Command: Create Task
Data: desc, status, assignee (User)
Event: Task.Assigned; optional: Task.Created

> Менеджеры или администраторы должны иметь кнопку «заассайнить задачи»

Actor: Manager or Admin User
Command: Reassign Tasks
Data: -
Event: Task.Assigned

> Каждый сотрудник должен иметь возможность ... отметить задачу выполненной.

Actor: User
Command: Close Task
Data: Task_id
Event: Task.Closed; optional: Task.Updated

### Accounting

> Аккаунтинг должен быть в отдельном дашборде и доступным только для администраторов и бухгалтеров.

Actor: User
Command: List Accounts | List Accounts filtered by User
Data: User Role
Event: -

> У каждого из сотрудников должен быть свой счёт, который показывает, сколько за сегодня он получил денег. У счёта должен быть аудитлог того, за что были списаны или начислены деньги, с подробным описанием каждой из задач.

Actor: User
Command: Detail Account
Data: User, Account id
Event: -

Actor: User
Command: List Transactions
Data: User, Account id
Event: -

> В конце дня необходимо: считать сколько денег сотрудник получил за рабочий день ...

Actor: cron
Command: Make User Invoices
Data: Tasks joined by User joined by Account
Event: Transaction.Created

> ... и отправлять на почту сумму выплаты.

Actor: Transaction.Created
Command: Make Payment & Send Email
Data: Transaction id
Event: Transaction.Processed, Account.FinalizedForTheDay

> После выплаты баланса (в конце дня) он должен обнуляться

This will automatically happen as a result of transaction.

### Analytics

> Нужно показывать самую дорогую задачу за день, неделю или месяц.

Actor: Task.Created
Command: Update analytics dashboard
Data: Task
Event: -

## HW0

[Miro Link](https://miro.com/app/board/uXjVPTrIHgk=/?share_link_id=879380577449)

<img src="./img/0.pngs">
