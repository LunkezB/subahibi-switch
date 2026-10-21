# Изменения «Чудесных дней» для Switch (тексты и настройки).
#
# Тексты меняем через перевод игры (config.language = "russian"): экраны
# игры остаются как есть, а если строки в другой версии APK нет, перевод
# просто не сработает.
#
# «Switch версия» в главном меню нарисована в картинках — её делает
# patch/assets.py при сборке.


# Варианты экранов. Порт VienDesu в init задаёт свой список
# (config.variants = phone/tablet/touch/ios/pc), и на Switch он затирает
# варианты движка: small/phone/touch/switch/mobile в портативе,
# large/tv/switch/mobile в док-станции. Возвращаем варианты движка, чтобы
# игра знала, что она на консоли: из меню игры пропадают «Помощь» (по
# клавиатуре и мыши) и «Выход» (выход есть в главном меню), а касания
# работают только в портативном режиме.

init -999 python:
    _subahibi_engine_variants = list(config.variants)

init 999 python:
    config.variants = list(_subahibi_engine_variants)


# «Об игре»: на Switch нет браузера, поэтому вместо ссылок Telegram и VK
# показываем адреса обычным текстом (цветом ссылок, но без перехода) и
# добавляем строку о Switch-порте.

translate russian strings:

    old "Автор перевода - ALexei101_mercurio\n\nАвторы порта - Innocence translations\n\n{a=https://t.me/innocence_translations}Telegram{/a}\n\n{a=https://vk.com/innocence_translations}VK{/a}"
    new "Автор перевода - ALexei101_mercurio\n\nАвторы порта - Innocence translations\n\n{color=#ffe08a}t.me/innocence_translations{/color}\n\n{color=#ffe08a}vk.com/innocence_translations{/color}"

    old "Оригинал: KeroQ\nAndroid-порт на Ren’Py"
    new "Оригинал: KeroQ\nAndroid-порт на Ren’Py\nПорт на Nintendo Switch: на основе Android-порта\n{color=#ffe08a}github.com/LunkezB/subahibi-switch{/color}"
