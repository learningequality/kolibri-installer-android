package org.learningequality.Kolibri.task;

import android.content.Context;
import android.util.Log;

import androidx.work.ExistingWorkPolicy;
import androidx.work.OneTimeWorkRequest;
import androidx.work.multiprocess.RemoteWorkManager;

import org.learningequality.ContextUtil;
import org.learningequality.FuturesUtil;
import org.learningequality.Kolibri.R;
import org.learningequality.Kolibri.sqlite.JobStorage;
import org.learningequality.sqlite.query.UpdateQuery;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicBoolean;

import java9.util.concurrent.CompletableFuture;


public class Reconciler implements AutoCloseable {
    public static final String TAG = "Kolibri.TaskReconciler";
    private static final AtomicBoolean lock = new AtomicBoolean(false);

    private final RemoteWorkManager workManager;
    private final JobStorage db;
    private final Executor executor;

    public Reconciler(RemoteWorkManager workManager, JobStorage db, Executor executor) {
        this.workManager = workManager;
        this.db = db;
        this.executor = executor;
    }

    /**
     * Create a new Reconciler instance from a Context
     * @param context The context to use
     * @return A new Reconciler instance
     */
    public static Reconciler from(Context context, JobStorage db, Executor executor) throws RuntimeException {
        // Ensure that we're in the task worker process
        String expectedProcessSuffix = context.getString(R.string.task_worker_process);
        String currentProcessName = ContextUtil.getCurrentProcessName(context);
        if (!currentProcessName.endsWith(expectedProcessSuffix)) {
            throw new RuntimeException("Refusing to create Reconciler in process " + currentProcessName);
        }
        RemoteWorkManager workManager = RemoteWorkManager.getInstance(context);
        return new Reconciler(workManager, db, executor);
    }

    /**
     * Synchronizes on the atomic boolean as a locking mechanism, which will prevent multiple
     * Reconciler instances from running at the same time. Reconciler.from already prevents this
     * from running in multiple processes.
     * @return True if the lock was acquired, false otherwise
     */
    public boolean begin() {
        // First get a lock on the lock file
        Log.d(TAG, "Acquiring lock");
        synchronized (lock) {
            if (lock.get()) {
                Log.d(TAG, "Lock already acquired");
                return false;
            }
            lock.set(true);
        }

        return true;
    }

    /**
     * Commit the database transaction and release the lock
     */
    public void end() {
        Log.d(TAG, "Releasing lock");
        synchronized (lock) {
            lock.set(false);
        }
    }

    /**
     * Close the Reconciler, rolling back the database transaction and releasing the lock
     */
    public void close() {
        // this may be a no-op if closing normally
        db.rollback();
        end();
    }

    /**
     * (Re)enqueue a WorkRequest from a Sentinel.Result
     * @param result The result of a Sentinel check operation
     */
    protected CompletableFuture<Void> enqueueFrom(Sentinel.Result result) {
        // We prefer to create the builder from the WorkInfo, if it exists
        Builder.TaskRequest builder = (result.isMissing())
                ? Builder.TaskRequest.fromJob(result.getJob())
                : Builder.TaskRequest.fromWorkInfo(result.getWorkInfo());


        if (result.isMissing()) {
            // if we're missing the WorkInfo, then we can't know if it's supposed to be long running,
            // because we don't track `long_running` in the DB, so we can only assume
            builder.setLongRunning(true)
                   .setDelay(0);
        }

        Log.d(TAG, "Re-enqueuing job " + builder.getId());
        OneTimeWorkRequest req = builder.build();

        // Using `REPLACE` here because we want to replace the existing request as a more
        // forceful way of ensuring that the request is enqueued, since this is reconciliation
        CompletableFuture<Void> future = FuturesUtil.toCompletable(
                workManager.enqueueUniqueWork(builder.getId(), ExistingWorkPolicy.REPLACE, req), executor
        );

        // Update the request ID in the database
        if (updateRequestId(builder.getId(), req.getId()) == 0) {
            Log.e(TAG, "Failed to update request ID for job " + builder.getId());
        }

        return future;
    }

    /**
     * Update the request ID for a job in the database
     * @param id The job ID
     * @param requestId The new WorkManager request ID
     * @return The number of rows updated
     */
    protected int updateRequestId(String id, UUID requestId) {
        Log.d(TAG, "Updating request ID for job " + id + " to " + requestId);
        UpdateQuery q = new UpdateQuery(JobStorage.Jobs.TABLE_NAME)
                .where(JobStorage.Jobs.id, id)
                .set(JobStorage.Jobs.worker_extra, requestId.toString());
        return q.execute(db);
    }

    /**
     * Process results from Sentinel checks that found jobs in the given state didn't match
     * the expected WorkManager state, or were missing
     * @param stateRef The state which Kolibri thinks the job is in
     * @param results The results of the Sentinel checks
     */
    public CompletableFuture<Void> process(StateMap stateRef, Sentinel.Result[] results) {
        Log.d(TAG, "Reconciling " + results.length + " jobs for state " + stateRef);
        List<CompletableFuture<Void>> futures = new ArrayList<CompletableFuture<Void>>();

        for (Sentinel.Result result : results) {
            switch (stateRef.getJobState()) {
                case PENDING:
                case QUEUED:
                case SCHEDULED:
                case SELECTED:
                case RUNNING:
                    futures.add(enqueueFrom(result));
                    break;
                default:
                    Log.d(TAG, "No reconciliation for state " + stateRef.getJobState());
                    break;
            }
        }

        // Wait for all the job enqueues to finish
        return CompletableFuture.allOf(futures.toArray(new CompletableFuture[0]));
    }
}
