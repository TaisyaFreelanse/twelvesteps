-- SQL скрипт для полной очистки данных пользователя с telegram_id = '125030399'
-- ВНИМАНИЕ: Этот скрипт удалит ВСЕ данные пользователя, но сохранит запись в таблице users
-- Находим user_id по telegram_id
DO $$
DECLARE
    target_user_id INTEGER;
BEGIN
    SELECT id INTO target_user_id FROM users WHERE telegram_id = '125030399';
    IF target_user_id IS NULL THEN
        RAISE EXCEPTION 'Пользователь с telegram_id = 125030399 не найден';
    END IF;
    RAISE NOTICE 'Найден пользователь с ID: %', target_user_id;
    DELETE FROM profile_section_data WHERE user_id = target_user_id;
    DELETE FROM profile_answers WHERE user_id = target_user_id;
    DELETE FROM template_progress WHERE user_id = target_user_id;
    DELETE FROM step10_daily_analysis WHERE user_id = target_user_id;
    DELETE FROM step_answers WHERE user_id = target_user_id;
    DELETE FROM user_steps WHERE user_id = target_user_id;
    DELETE FROM tails WHERE user_id = target_user_id;
    DELETE FROM messages WHERE user_id = target_user_id;
    DELETE FROM frames WHERE user_id = target_user_id;
    DELETE FROM session_contexts WHERE user_id = target_user_id;
    DELETE FROM session_states WHERE user_id = target_user_id;
    DELETE FROM frame_tracking WHERE user_id = target_user_id;
    DELETE FROM qa_status WHERE user_id = target_user_id;
    DELETE FROM user_meta WHERE user_id = target_user_id;
    DELETE FROM tracker_summaries WHERE user_id = target_user_id;
    DELETE FROM gratitudes WHERE user_id = target_user_id;
    DELETE FROM answer_templates WHERE user_id = target_user_id;
    DELETE FROM profile_sections WHERE user_id = target_user_id;
    UPDATE users 
    SET 
        personal_prompt = NULL,
        program_experience = NULL,
        sobriety_date = NULL,
        active_template_id = NULL,
        relapse_dates = NULL,
        sponsor_ids = NULL,
        custom_fields = NULL,
        last_active = NULL,
        updated_at = NOW()
    WHERE id = target_user_id;
    RAISE NOTICE 'Все данные пользователя с ID % успешно удалены', target_user_id;
    RAISE NOTICE 'Запись пользователя сохранена, но все поля обнулены';
END $$;
-- Проверка: показываем, что осталось
SELECT 
    'users' as table_name, 
    COUNT(*) as remaining_records 
FROM users 
WHERE telegram_id = '125030399'
UNION ALL
SELECT 'profile_section_data', COUNT(*) FROM profile_section_data WHERE user_id = (SELECT id FROM users WHERE telegram_id = '125030399')
UNION ALL
SELECT 'profile_answers', COUNT(*) FROM profile_answers WHERE user_id = (SELECT id FROM users WHERE telegram_id = '125030399')
UNION ALL
SELECT 'messages', COUNT(*) FROM messages WHERE user_id = (SELECT id FROM users WHERE telegram_id = '125030399')
UNION ALL
SELECT 'frames', COUNT(*) FROM frames WHERE user_id = (SELECT id FROM users WHERE telegram_id = '125030399')
UNION ALL
SELECT 'step_answers', COUNT(*) FROM step_answers WHERE user_id = (SELECT id FROM users WHERE telegram_id = '125030399');