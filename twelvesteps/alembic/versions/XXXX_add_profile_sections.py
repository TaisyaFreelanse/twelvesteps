"""add_profile_sections

Revision ID: 0c9f04e7d5e7
Revises: 2d985e1a5f02
Create Date: 2025-01-20 12:00:00.000000

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String, Integer, Boolean, Text

# revision identifiers, used by Alembic.
revision: str = '0c9f04e7d5e7'
down_revision: Union[str, Sequence[str], None] = '2d985e1a5f02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create profile_sections table
    op.create_table(
        'profile_sections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('icon', sa.String(length=10), nullable=True),
        sa.Column('is_custom', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_profile_sections_user_id'), 'profile_sections', ['user_id'], unique=False)
    op.create_index(op.f('ix_profile_sections_order_index'), 'profile_sections', ['order_index'], unique=False)

    # Create profile_section_data table
    op.create_table(
        'profile_section_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['section_id'], ['profile_sections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_profile_section_data_user_id'), 'profile_section_data', ['user_id'], unique=False)
    op.create_index(op.f('ix_profile_section_data_section_id'), 'profile_section_data', ['section_id'], unique=False)

    # Create profile_questions table
    op.create_table(
        'profile_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_optional', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['section_id'], ['profile_sections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_profile_questions_section_id'), 'profile_questions', ['section_id'], unique=False)
    op.create_index(op.f('ix_profile_questions_order_index'), 'profile_questions', ['order_index'], unique=False)

    # Create profile_answers table
    op.create_table(
        'profile_answers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('answer_text', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['profile_questions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'question_id', 'version', name='uq_profile_answer_version')
    )
    op.create_index(op.f('ix_profile_answers_user_id'), 'profile_answers', ['user_id'], unique=False)
    op.create_index(op.f('ix_profile_answers_question_id'), 'profile_answers', ['question_id'], unique=False)

    # Insert initial data for standard sections
    profile_sections = table(
        'profile_sections',
        column('id', Integer),
        column('name', String),
        column('icon', String),
        column('is_custom', Boolean),
        column('user_id', Integer),
        column('order_index', Integer),
    )

    profile_questions = table(
        'profile_questions',
        column('id', Integer),
        column('section_id', Integer),
        column('question_text', Text),
        column('order_index', Integer),
        column('is_optional', Boolean),
    )

    # Standard sections with their questions
    sections_data = [
        (1, '👨‍👩‍👧 Семья', '👨‍👩‍👧', False, None, 1),
        (2, '🧑‍🤝‍🧑 Друзья', '🧑‍🤝‍🧑', False, None, 2),
        (3, '🎓 Учёба', '🎓', False, None, 3),
        (4, '🧒 Детство', '🧒', False, None, 4),
        (5, '❤️ Любимые занятия', '❤️', False, None, 5),
        (6, '🎯 Хобби', '🎯', False, None, 6),
        (7, '💼 Работа / Дело', '💼', False, None, 7),
        (8, '🤝 Поддержка рядом', '🤝', False, None, 8),
        (9, '🕒 Режим и быт', '🕒', False, None, 9),
        (10, '🧭 Ценности и правила', '🧭', False, None, 10),
        (11, '🛑 Границы и темы "пока не трогать"', '🛑', False, None, 11),
        (12, '💪 Сильные стороны', '💪', False, None, 12),
        (13, '🩺 Здоровье', '🩺', False, None, 13),
        (14, '✍️ Свободный рассказ', '✍️', False, None, 14),
    ]

    questions_data = [
        # Семья (section_id=1)
        (1, 1, 'Какая роль была у тебя в семье, когда ты рос?', 1, False),
        (2, 1, 'Был ли у тебя кто-то в семье, кто принимал тебя любым?', 2, False),
        (3, 1, 'Какие темы в семье было не принято обсуждать?', 3, False),
        (4, 1, 'Как сейчас проявляется связь с семьёй? Что поддерживает, а что ранит?', 4, False),
        # Друзья (section_id=2)
        (5, 2, 'Когда ты в последний раз чувствовал(а), что тебя по‑настоящему понимают?', 1, False),
        (6, 2, 'С кем ты можешь говорить честно — без масок и страха быть осуждённым?', 2, False),
        (7, 2, 'Как часто ты ощущаешь себя одиноким, даже среди людей?', 3, False),
        (8, 2, 'Как ты обычно заканчиваешь близкие отношения?', 4, False),
        # Учёба (section_id=3)
        (9, 3, 'Что тебе в учёбе всегда давалось легко — как будто \'своё\'?', 1, False),
        (10, 3, 'Была ли ситуация, когда кто-то в учёбе тебя сломал или обесценил?', 2, False),
        (11, 3, 'Как ты относишься к себе, когда не справляешься с задачей?', 3, False),
        (12, 3, 'Если бы не было страха провала — чему бы ты хотел(а) научиться?', 4, False),
        # Детство (section_id=4)
        (13, 4, 'Что первое приходит на ум, когда ты вспоминаешь детство?', 1, False),
        (14, 4, 'Какая сцена из детства тебе запомнилась как очень светлая?', 2, False),
        (15, 4, 'Кем ты мечтал(а) стать в детстве и как это изменилось?', 3, False),
        (16, 4, 'Какая травма или трудность из детства до сих пор отзывается?', 4, True),
        # Любимые занятия (section_id=5)
        (17, 5, 'Что ты делал(а) раньше, что приносило радость просто потому что нравилось?', 1, False),
        (18, 5, 'Когда ты последний раз позволял(а) себе делать что-то просто для себя?', 2, False),
        (19, 5, 'Есть ли у тебя что-то, что ты давно хочешь вернуть в свою жизнь?', 3, False),
        (20, 5, 'Что тебя обычно возвращает к жизни, даже в сложные дни?', 4, False),
        # Хобби (section_id=6)
        (21, 6, 'Есть ли у тебя хобби, в которое ты полностью уходишь?', 1, False),
        (22, 6, 'Когда в последний раз ты чувствовал(а) вдохновение?', 2, False),
        (23, 6, 'Какие мелочи тебе нравятся делать руками или головой?', 3, False),
        (24, 6, 'Если бы у тебя был один свободный день — на что бы ты его потратил(а)?', 4, False),
        # Работа / Дело (section_id=7)
        (25, 7, 'Что в твоей работе или деле тебя наполняет?', 1, False),
        (26, 7, 'Что больше всего истощает или раздражает в твоём текущем занятии?', 2, False),
        (27, 7, 'Есть ли у тебя мечта или проект, который ты пока не реализовал(а)?', 3, False),
        (28, 7, 'Чего бы ты точно не хотел(а) делать в будущем — ни за какие деньги?', 4, False),
        # Поддержка рядом (section_id=8)
        (29, 8, 'Кто рядом с тобой сейчас и действительно \'за тебя\'?', 1, False),
        (30, 8, 'Какую поддержку ты бы хотел(а) получать, но не получаешь?', 2, False),
        (31, 8, 'Чего тебе не хватает в отношениях с людьми?', 3, False),
        (32, 8, 'Ты умеешь просить о помощи, когда трудно?', 4, False),
        # Режим и быт (section_id=9)
        (33, 9, 'Какая часть твоего дня обычно проходит спокойно?', 1, False),
        (34, 9, 'Есть ли у тебя устойчивый утренний или вечерний ритуал?', 2, False),
        (35, 9, 'Что бы ты хотел(а) улучшить в своём распорядке?', 3, False),
        (36, 9, 'Какая мелочь в быту даёт тебе ощущение стабильности?', 4, False),
        # Ценности и правила (section_id=10)
        (37, 10, 'Какие три принципа в жизни для тебя нерушимы?', 1, False),
        (38, 10, 'Бывали ли моменты, когда ты предавал(а) свои ценности?', 2, False),
        (39, 10, 'Что для тебя \'жить честно\'?', 3, False),
        (40, 10, 'Какие внутренние правила ты хотел(а) бы поменять?', 4, False),
        # Границы и темы "пока не трогать" (section_id=11)
        (41, 11, 'О чём ты точно не хочешь сейчас говорить?', 1, False),
        (42, 11, 'Какие темы для тебя особенно чувствительны?', 2, False),
        (43, 11, 'Какая реакция со стороны других тебя закрывает?', 3, False),
        (44, 11, 'Когда ты понимаешь, что тебе пора остановиться?', 4, False),
        # Сильные стороны (section_id=12)
        (45, 12, 'В каких ситуациях ты гордишься собой?', 1, False),
        (46, 12, 'Что у тебя получается особенно хорошо — даже если ты это не признаёшь?', 2, False),
        (47, 12, 'Какие черты в себе ты считаешь ресурсом?', 3, False),
        (48, 12, 'Когда ты чувствуешь, что ты силён(сильна)?', 4, False),
        # Здоровье (section_id=13)
        (49, 13, 'Как ты сейчас чувствуешь своё тело?', 1, False),
        (50, 13, 'Есть ли темы в здоровье, которые вызывают страх или напряжение?', 2, True),
        (51, 13, 'Что помогает тебе восстанавливаться физически или эмоционально?', 3, False),
        (52, 13, 'Ты чувствуешь, когда организм говорит \'стоп\'?', 4, False),
        # Свободный рассказ (section_id=14) - без вопросов, только свободный ввод
    ]

    # Insert sections
    op.bulk_insert(profile_sections, [
        {'id': sid, 'name': name, 'icon': icon, 'is_custom': is_custom, 'user_id': user_id, 'order_index': order_idx}
        for sid, name, icon, is_custom, user_id, order_idx in sections_data
    ])

    # Insert questions
    op.bulk_insert(profile_questions, [
        {'id': qid, 'section_id': sid, 'question_text': text, 'order_index': order_idx, 'is_optional': is_opt}
        for qid, sid, text, order_idx, is_opt in questions_data
    ])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_profile_answers_question_id'), table_name='profile_answers')
    op.drop_index(op.f('ix_profile_answers_user_id'), table_name='profile_answers')
    op.drop_table('profile_answers')
    op.drop_index(op.f('ix_profile_questions_order_index'), table_name='profile_questions')
    op.drop_index(op.f('ix_profile_questions_section_id'), table_name='profile_questions')
    op.drop_table('profile_questions')
    op.drop_index(op.f('ix_profile_section_data_section_id'), table_name='profile_section_data')
    op.drop_index(op.f('ix_profile_section_data_user_id'), table_name='profile_section_data')
    op.drop_table('profile_section_data')
    op.drop_index(op.f('ix_profile_sections_order_index'), table_name='profile_sections')
    op.drop_index(op.f('ix_profile_sections_user_id'), table_name='profile_sections')
    op.drop_table('profile_sections')

