package org.learningequality.sqlite.schema;

import android.os.Bundle;

public interface DatabaseTable {
    String DATABASE_NAME = "DATABASE_NAME";
    String TABLE_NAME = "TABLE_NAME";

    String getTableName();

    interface Column<T> {
        String getColumnName();
    }

    interface ColumnEnum<T> extends Column<T> {
        String name();

        T getValue();

        ColumnImpl<T> getColumn();

        default String getColumnName() {
            return getColumn().getColumnName();
        }
    }

    interface StringChoiceEnum extends ColumnEnum<String> {
        default String getValue() {
            return this.name();
        }
    }

    abstract class ColumnImpl<T> implements Column<T> {
        private final String columnName;

        public ColumnImpl(String columnName) {
            this.columnName = columnName;
        }

        public String getColumnName() {
            return this.columnName;
        }
    }

    class StringColumn extends ColumnImpl<String> {
        public StringColumn(String columnName) {
            super(columnName);
        }

        public String getValue(Bundle bundle) {
            return bundle.getString(getColumnName());
        }
    }

    class LongColumn extends ColumnImpl<Long> {
        public LongColumn(String columnName) {
            super(columnName);
        }

        public Long getValue(Bundle bundle) {
            return bundle.getLong(getColumnName());
        }
    }
}
